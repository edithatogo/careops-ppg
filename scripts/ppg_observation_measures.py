"""Observation arithmetic for the existing process-reporting CLI and CSV format."""
import csv
import hashlib
import io
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ['datasetKind','asOf','walkthroughId','task','outcome','durationSeconds',
            'missingInputCount','helpRequired','correctionCount','exclusionReason']


def observation_report(text):
    contract_bytes = (ROOT/'config/observation-measures.json').read_bytes()
    contract = json.loads(contract_bytes)
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames) or set(REQUIRED) - set(reader.fieldnames):
        raise ValueError('Observation CSV headers missing or duplicated')
    rows, seen, kinds = [], set(), set()
    def number(value, count=False):
        if value == '': return None
        if not re.fullmatch(r'[0-9]+' if count else r'[0-9]+(?:\.[0-9]+)?', value):
            raise ValueError('Expected nonnegative finite observation number')
        result = int(value) if count else float(value)
        try:
            if not math.isfinite(result): raise ValueError('Nonfinite observation number')
        except OverflowError as exc:
            raise ValueError('Observation number too large') from exc
        return result
    for index, raw in enumerate(reader, 2):
        if None in raw or any(v is None for v in raw.values()):
            raise ValueError('Observation CSV row width differs from header')
        row = {k:v.strip() for k,v in raw.items()}
        if row['task'] not in contract['tasks'] or row['outcome'] not in contract['outcomes']:
            raise ValueError('Unknown observation task or outcome')
        row['method'] = row.get('method') or 'unclassified'
        if row['method'] not in contract['methods']: raise ValueError('Unknown observation method')
        for key in ['durationSeconds','stageWaitSeconds','missingInputCount','correctionCount']:
            row[key] = number(row.get(key,''), key.endswith('Count'))
        if row['helpRequired'] not in ['','yes','no']: raise ValueError('Unknown help response')
        if row['outcome'] == 'not-observed':
            if any(row[k] is not None for k in ['durationSeconds','stageWaitSeconds','missingInputCount','correctionCount']) or row['helpRequired']:
                raise ValueError('Not-observed task cannot contain observed measures')
        if row['datasetKind']:
            if row['datasetKind'] not in ['operational','fictional']: raise ValueError('Unknown observation dataset')
            kinds.add(row['datasetKind'])
        if row['outcome'] != 'not-observed':
            if not row['datasetKind'] or not row['walkthroughId'] or not row['asOf']:
                raise ValueError('Observed task requires dataset, walkthrough and timestamp')
            moment = datetime.fromisoformat(row['asOf'].replace('Z','+00:00'))
            if moment.utcoffset() is None: raise ValueError('Observation timestamp timezone required')
            if (row['outcome'] in ['held','failed'] or row['durationSeconds'] is None) and not row['exclusionReason']:
                raise ValueError('Held/failed or missing timing requires exclusion reason')
        identity = (row['walkthroughId'], row['task'])
        if row['walkthroughId'] and identity in seen: raise ValueError('Duplicate walkthrough task')
        if row['walkthroughId']: seen.add(identity)
        row['_row'] = index
        rows.append(row)
    if len(kinds)>1: raise ValueError('Fictional and operational observations must stay separate')
    kind = next(iter(kinds),'unobserved-template')
    groups = defaultdict(list)
    for row in rows: groups[(row['method'],row['task'])].append(row)
    def summary(group):
        attempted = [r for r in group if r['outcome']!='not-observed']
        completed = [r for r in attempted if r['outcome']=='completed']
        def timing(key):
            values = [r[key] for r in completed if r[key] is not None]
            return {'sampleCount':len(values),'totalSeconds':sum(values) if values else None,
                    'medianSeconds':median(values) if values else None,
                    'completedMissingCount':sum(r[key] is None for r in completed),
                    'noncompletedExcludedCount':len(attempted)-len(completed)}
        def count(key):
            values = [r[key] for r in attempted if r[key] is not None]
            return {'total':sum(values) if values else None,'knownTaskCount':len(values),'unknownTaskCount':len(attempted)-len(values)}
        known_help = [r for r in attempted if r['helpRequired']]
        return {'attemptedTasks':len(attempted),'outcomes':dict(Counter(r['outcome'] for r in group)),
                'handsOn':timing('durationSeconds'),'stageWait':timing('stageWaitSeconds'),
                'help':{'yesCount':sum(r['helpRequired']=='yes' for r in known_help),'knownTaskCount':len(known_help),
                        'unknownTaskCount':len(attempted)-len(known_help)},
                'missingInputs':count('missingInputCount'),'corrections':count('correctionCount')}
    pairs = defaultdict(dict)
    exclusions = []
    for row in rows:
        if not row.get('pairId'):
            if row['outcome']!='not-observed': exclusions.append({'row':row['_row'],'reason':'no-pair-reference'})
            continue
        if row['method'] not in ['baseline','workbench']: raise ValueError('Paired task requires baseline/workbench method')
        key = (row['pairId'],row['task'])
        if row['method'] in pairs[key]: raise ValueError('Duplicate method within matched task pair')
        pairs[key][row['method']] = row
    differences = defaultdict(list)
    for (_,task), pair in pairs.items():
        values = list(pair.values()); reason = None
        if set(pair) != {'baseline','workbench'}: reason = 'missing-counterpart'
        elif any(not r.get(k) for r in values for k in contract['pairedIdentity']): reason = 'missing-match-identity'
        elif any(pair['baseline'][k]!=pair['workbench'][k] for k in contract['pairedIdentity']): reason = 'input-period-version-or-variant-mismatch'
        elif any(r['outcome']!='completed' or r['durationSeconds'] is None for r in values): reason = 'incomplete-or-untimed-task'
        if reason:
            exclusions.append({'rows':[r['_row'] for r in values],'task':task,'reason':reason})
        else:
            differences[task].append(pair['baseline']['durationSeconds']-pair['workbench']['durationSeconds'])
    comparisons = {task:{'sampleCount':len(values),'medianBaselineMinusWorkbenchSeconds':median(values)} for task,values in sorted(differences.items())}
    report = {'schemaVersion':1,'datasetKind':kind,'status':'observations-recorded' if any(r['outcome']!='not-observed' for r in rows) else 'not-measured',
            'benefitConclusion':'Not measured' if kind!='operational' or not comparisons else 'Observed matched-task differences only; no causal benefit conclusion',
            'inputSHA256':hashlib.sha256(text.encode()).hexdigest(),'dictionarySHA256':hashlib.sha256(contract_bytes).hexdigest(),
            'processDictionarySHA256':hashlib.sha256((ROOT/'config/process-measures.json').read_bytes()).hexdigest(),
            'observationCount':len(rows),'walkthroughCount':len({r['walkthroughId'] for r in rows if r['outcome']!='not-observed'}),'observationDates':sorted({r['asOf'] for r in rows if r['outcome']!='not-observed'}),
            'sourceContext':[{k:r.get(k,'') for k in ['asOf','walkthroughId','task','method','pairId',*contract['pairedIdentity']]} for r in rows],
            'summary':summary(rows),'byMethodAndTask':{method+'/'+task:summary(group) for (method,task),group in sorted(groups.items())},
            'comparisons':comparisons,'comparisonExclusions':exclusions,
            'observationExclusions':[{'row':r['_row'],'task':r['task'],'outcome':r['outcome'],'reason':r['exclusionReason']} for r in rows if r['outcome']!='completed' or r['durationSeconds'] is None],
            'itemWrites':0}
    # Finite inputs can still overflow when summed or averaged. Refuse the report
    # before the CLI creates any output rather than exporting Infinity as a measure.
    json.dumps(report, allow_nan=False)
    return report


def observation_csv(report):
    """Only fixed dictionary keys and computed values; never free-text CSV cells."""
    stream = io.StringIO(newline=''); writer=csv.writer(stream)
    writer.writerow(['datasetKind','methodTask','measure','value','denominator','inputSHA256'])
    for group, values in report['byMethodAndTask'].items():
        for name in ['handsOn','stageWait']:
            writer.writerow([report['datasetKind'],group,name+'MedianSeconds',values[name]['medianSeconds'],values[name]['sampleCount'],report['inputSHA256']])
        for name in ['missingInputs','corrections']:
            writer.writerow([report['datasetKind'],group,name,values[name]['total'],values[name]['knownTaskCount'],report['inputSHA256']])
        writer.writerow([report['datasetKind'],group,'helpYes',values['help']['yesCount'],values['help']['knownTaskCount'],report['inputSHA256']])
    for task,values in report['comparisons'].items():
        writer.writerow([report['datasetKind'],'matched/'+task,'baselineMinusWorkbenchSeconds',values['medianBaselineMinusWorkbenchSeconds'],values['sampleCount'],report['inputSHA256']])
    return stream.getvalue()
