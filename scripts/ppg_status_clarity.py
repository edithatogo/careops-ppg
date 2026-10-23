#!/usr/bin/env python3
"""Prepare presentation JSON for the existing status view; no tenant writes."""
from datetime import datetime, timedelta, timezone
import json
import re

UNKNOWN='Reconciliation state cannot be confirmed'
LABELS={'healthy':'Source matches the last verified reconciliation','held':'Source change detected—reconciliation held','failed':'Latest reconciliation failed or remains unverified','unknown':UNKNOWN}

def parse_utc(value):
    if not isinstance(value,str):return None
    try:
        d=datetime.fromisoformat(value.replace('Z','+00:00'))
        return d.astimezone(timezone.utc) if d.tzinfo else None
    except ValueError:return None

def presentation(row, now):
    """Do not mutate the row, replace baseline time or erase a recorded failure."""
    projected=parse_utc(row.get('ProjectedAt'));check=parse_utc(row.get('LatestCheck'));baseline=parse_utc(row.get('LastSuccessfulReconciliation'))
    fresh='unknown' if projected is None or projected>now else 'stale' if (now-projected).total_seconds()>1800 else 'fresh'
    recorded=row.get('Health','unknown');effective=recorded if recorded in LABELS else 'unknown'
    valid=(projected is not None and check is not None and baseline is not None and
           projected<=now and check<=now and baseline<=now and check<=projected and baseline<=projected)
    overdue=check is not None and check<=now and (now-check).total_seconds()>5400
    if not valid:effective='unknown'
    if effective=='healthy' and (overdue or not row.get('ObservedVersion') or row.get('ObservedVersion')!=row.get('CommittedVersion') or type(row.get('CommittedCount')) not in [int,float] or row['CommittedCount']<1):effective='unknown'
    def clock(v):
        d=parse_utc(v)
        return d.astimezone(timezone(timedelta(hours=10))).strftime('%Y-%m-%d %H:%M:%S AEST (UTC+10)') if d else 'Unavailable — timestamp not recorded'
    return {'effective':effective,'recorded':recorded,'stateLabel':LABELS[effective],'freshness':fresh,'sourceCheckOverdue':overdue,'reason':row.get('Reason') or 'Reason unavailable','nextAction':row.get('NextAction') or 'Inspect existing evidence','clocks':{k:clock(row.get(k)) for k in ['LatestCheck','LastSuccessfulReconciliation','ProjectedAt']},'committedCount':row.get('CommittedCount')}

def numeric(field):return 'Number(Date('+field+'))'
def valid_time(field):
    n=numeric(field)
    return "length("+field+") > 0 && "+n+' == '+n+' && '+n+' <= Number(@now)'

def brisbane_clock(field):
    """Fixed UTC+10 civil-date arithmetic: independent of browser/site timezone.

    Shallow text parts use only supported arithmetic/date operators.
    Gregorian civil-from-days decomposition uses the Unix epoch offset 719468.
    No user content, calculations or authoritative fields are changed.
    """
    bindings=[('z','floor(('+numeric(field)+' + 36000000) / 86400000) + 719468'),
              ('era','floor(Number([$z]) / 146097)'),
              ('doe','Number([$z]) - Number([$era]) * 146097'),
              ('yoe','floor((Number([$doe]) - floor(Number([$doe]) / 1460) + floor(Number([$doe]) / 36524) - floor(Number([$doe]) / 146096)) / 365)'),
              ('y0','Number([$yoe]) + Number([$era]) * 400'),
              ('doy','Number([$doe]) - (365 * Number([$yoe]) + floor(Number([$yoe]) / 4) - floor(Number([$yoe]) / 100))'),
              ('mp','floor((5 * Number([$doy]) + 2) / 153)'),
              ('day','Number([$doy]) - floor((153 * Number([$mp]) + 2) / 5) + 1'),
              ('month','Number([$mp]) + if(Number([$mp]) < 10,3,-9)'),
              ('year','Number([$y0]) + if(Number([$month]) <= 2,1,0)'),
              ('seconds','floor(('+numeric(field)+' + 36000000) / 1000) % 86400')]
    def pad(expr):return "if("+expr+" < 10,'0','') + toString("+expr+")"
    text="toString([$year]) + '-' + "+pad('Number([$month])')+" + '-' + "+pad('Number([$day])')+" + ' ' + "+pad('floor(Number([$seconds]) / 3600)')+" + ':' + "+pad('floor((Number([$seconds]) % 3600) / 60)')+" + ':' + "+pad('Number([$seconds]) % 60')+" + ' AEST (UTC+10)'"
    # Native nested-loop rendering was unavailable on the checked route. Expand
    # arithmetic into independent text parts, keeping the rendered DOM shallow.
    expanded={}
    for name,expr in bindings:
        expr=re.sub(r'Number\(\[\$(\w+)\]\)',lambda m:'('+expanded[m[1]]+')' if m[1] in expanded else m[0],expr)
        expanded[name]=expr
    parts=["toString([$year])", "'-'",pad('Number([$month])'),"'-'",pad('Number([$day])'),"' '",pad('floor(Number([$seconds]) / 3600)'),"':'",pad('floor((Number([$seconds]) % 3600) / 60)'),"':'",pad('Number([$seconds]) % 60'),"' AEST (UTC+10)'"]
    children=[]
    for part in parts:
        part=re.sub(r'Number\(\[\$(\w+)\]\)',lambda m:'('+expanded[m[1]]+')' if m[1] in expanded else m[0],part)
        part=re.sub(r'\[\$(\w+)\]',lambda m:'('+expanded[m[1]]+')' if m[1] in expanded else m[0],part)
        children.append({'elmType':'span','txtContent':part[1:-1] if part.startswith("'") and part.endswith("'") else '='+part})
    node={'elmType':'span','children':children}
    finite='length('+field+') > 0 && '+numeric(field)+' == '+numeric(field)
    return {'elmType':'div','children':[{'elmType':'span','style':{'display':"=if("+finite+", 'none', 'inline')"},'txtContent':'Unavailable — missing or invalid timestamp'},{'elmType':'span','style':{'display':"=if("+finite+", 'inline', 'none')"},'children':[node]}]}


def view_formatter(identity_guide,evidence_view,site_root=None):
    fields={x:'[$'+x+']' for x in ['ProjectedAt','LatestCheck','LastSuccessfulReconciliation']}
    valid=' && '.join('('+valid_time(f)+')' for f in fields.values())+' && Number(Date([$LatestCheck])) <= Number(Date([$ProjectedAt])) && Number(Date([$LastSuccessfulReconciliation])) <= Number(Date([$ProjectedAt]))'
    fresh="if("+valid_time(fields['ProjectedAt'])+",if(Number(@now) - Number(Date([$ProjectedAt])) > 1800000,'Status display is stale—last known state shown','Status display recently updated'),'Status display freshness cannot be confirmed')"
    badhealthy="Number(@now) - Number(Date([$LatestCheck])) > 5400000 || [$ObservedVersion] == '' || [$CommittedVersion] == '' || [$ObservedVersion] != [$CommittedVersion] || [$CommittedCount] < 1"
    labels="if([$Health] == 'held','"+LABELS['held']+"',if([$Health] == 'failed','"+LABELS['failed']+"',if([$Health] == 'healthy',if("+badhealthy+",'"+UNKNOWN+"','"+LABELS['healthy']+"'),'"+UNKNOWN+"')))"
    effective="=if("+valid+','+labels+",'"+UNKNOWN+"')"
    def line(label,value):return {'elmType':'div','style':{'margin-bottom':'8px','white-space':'normal'},'children':[{'elmType':'span','style':{'font-weight':'600'},'txtContent':label+' '},{'elmType':'span','txtContent':value}]}
    children=[line('Reconciliation state:',effective),line('Display freshness:','='+fresh),line('Recorded state — retained:','[$Health]'),line('Reason — retained:','[$Reason]'),line('What to do next:','[$NextAction]'),line('Latest reconciliation attempt:','[$LatestAttemptOutcome]')]
    for key,label in [('LatestCheck','Last source check'),('LastSuccessfulReconciliation','Last verified reconciliation'),('ProjectedAt','Status display updated')]:children.append({'elmType':'div','style':{'margin-bottom':'8px'},'children':[{'elmType':'div','style':{'font-weight':'600'},'txtContent':label},brisbane_clock(fields[key])]})
    children+=[line('Records in verified baseline:',"=if([$CommittedCount] == '', 'Unavailable — baseline count not recorded', toString([$CommittedCount]))"),line('Source-check freshness:',"=if("+valid_time(fields['LatestCheck'])+",if(Number(@now) - Number(Date([$LatestCheck])) > 5400000,'Source check overdue — cannot support healthy','Source check within 90 minutes'),'Source-check time unavailable or invalid')")]
    for label,url in [('Resolve identity hold — operator guide',identity_guide),('Inspect source/attempt evidence',evidence_view)]:children.append({'elmType':'a','style':{'display':'block','padding':'6px 0'},'attributes':{'href':url,'target':'_blank'},'txtContent':label})
    if site_root:
        children.append({'elmType':'a','style':{'display':"=if(indexOf([$EvidenceLink], '"+site_root+"/') == 0,'block','none')",'padding':'6px 0'},'attributes':{'href':'[$EvidenceLink]','target':'_blank'},'txtContent':'View recorded attempt receipt'})
    return {'$schema':'https://developer.microsoft.com/json-schemas/sp/v2/row-formatting.schema.json','hideColumnHeader':True,'rowFormatter':{'elmType':'div','style':{'display':'block','padding':'16px','border':'1px solid #8a8886','width':'100%'},'children':children}}
