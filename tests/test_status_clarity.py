import sys, unittest, json, subprocess
from pathlib import Path
from datetime import datetime,timedelta,timezone
from copy import deepcopy
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from ppg_status_clarity import presentation, view_formatter

class StatusClarityTests(unittest.TestCase):
 def setUp(self):
  self.now=datetime(2026,10,17,0,0,tzinfo=timezone.utc)
  self.row={'Health':'healthy','ProjectedAt':'2026-10-16T23:59:00Z','LatestCheck':'2026-10-16T23:30:00Z','LastSuccessfulReconciliation':'2026-10-14T20:03:46Z','ObservedVersion':'v1','CommittedVersion':'v1','CommittedCount':985,'Reason':'Retain this reason','NextAction':'Inspect same operation'}
 def test_held_failed_reason_and_baseline_survive_stale(self):
  for state in ['held','failed']:
   row={**self.row,'Health':state,'ProjectedAt':'2026-10-16T23:00:00Z','LatestCheck':'2026-10-16T22:30:00Z'};old=deepcopy(row);p=presentation(row,self.now)
   self.assertEqual((state,'stale'),(p['effective'],p['freshness']));self.assertEqual('Retain this reason',p['reason']);self.assertEqual(row,old);self.assertIn('2026-10-15 06:03:46',p['clocks']['LastSuccessfulReconciliation'])
 def test_future_missing_invalid_and_inconsistent_clocks(self):
  for key in ['ProjectedAt','LatestCheck','LastSuccessfulReconciliation']:
   for value in [None,'bad','2026-10-17T00:01:00Z']:
    p=presentation({**self.row,key:value},self.now);self.assertEqual('unknown',p['effective'])
  self.assertEqual('unknown',presentation({**self.row,'ProjectedAt':'2026-10-16T23:00:00Z'},self.now)['effective'])
 def test_exact_boundaries_mismatch_and_missing_baseline(self):
  for age,fresh in [(1800,'fresh'),(1801,'stale')]:
   r={**self.row,'ProjectedAt':(self.now-timedelta(seconds=age)).isoformat(),'LatestCheck':(self.now-timedelta(seconds=age+1)).isoformat()};self.assertEqual(fresh,presentation(r,self.now)['freshness'])
  for age,state in [(5400,'healthy'),(5401,'unknown')]:
   r={**self.row,'LatestCheck':(self.now-timedelta(seconds=age)).isoformat()};self.assertEqual(state,presentation(r,self.now)['effective'])
  self.assertEqual('unknown',presentation({**self.row,'ObservedVersion':'v2'},self.now)['effective'])
  p=presentation({**self.row,'LastSuccessfulReconciliation':None,'CommittedCount':None},self.now);self.assertIsNone(p['committedCount']);self.assertIn('Unavailable',p['clocks']['LastSuccessfulReconciliation'])
 def test_generated_native_expressions_match_independent_clock_and_states(self):
  rows=[self.row,{**self.row,'Health':'held','ObservedVersion':'v2'},{**self.row,'Health':'failed'},{**self.row,'Health':'unknown'},
        {**self.row,'Health':'held','ProjectedAt':'2026-10-16T23:00:00Z','LatestCheck':'2026-10-16T22:30:00Z'},
        {**self.row,'ProjectedAt':'2026-10-17T00:01:00Z'},{**self.row,'LatestCheck':None},{**self.row,'LatestCheck':'invalid'},
        {**self.row,'LastSuccessfulReconciliation':'2024-02-29T14:00:01Z'},{**self.row,'LastSuccessfulReconciliation':'2025-12-31T14:00:00Z'}]
  fmt=view_formatter('/identity','/evidence');cases=[{'row':r,'now':self.now.isoformat(),'formatter':fmt} for r in rows]
  result=subprocess.run(['node',str(ROOT/'tests/status_formatter_probe.cjs')],input=json.dumps(cases),text=True,capture_output=True,check=True);rendered=json.loads(result.stdout)
  for row,text in zip(rows,rendered):
   expected=presentation(row,self.now);self.assertIn(expected['stateLabel'],text);self.assertIn(row['Reason'],text)
   for value in expected['clocks'].values():
    if not value.startswith('Unavailable'):self.assertIn(value,text)
    else:self.assertIn('Unavailable',text)
  self.assertIn('Status display is stale',rendered[4]);self.assertIn('freshness cannot be confirmed',rendered[5])

if __name__=='__main__':unittest.main()
