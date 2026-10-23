import sys
from pathlib import Path
from datetime import date
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ppg_guided_workspace import target_state, row_formatter, target_expression, bind_form, formatter_json

class GuidedWorkspaceTests(unittest.TestCase):
    def test_form_binding_preserves_template(self):
        template={"href":"='{{workspacePath}}/Lists/Review'"}
        self.assertEqual({"href":"='/sites/ppg/Lists/Review'"},bind_form(template,"/sites/ppg"))
        self.assertIn("{{workspacePath}}",template["href"])
        with self.assertRaises(ValueError):bind_form(template,"https://other.example")

    def test_xml_backed_json_round_trip(self):
        import json
        value={"expression":"=if(a < b && b > c,1,0)","href":"/x?a=1&b=2"}
        encoded=formatter_json(value)
        self.assertFalse(any(c in encoded for c in "&<>"))
        self.assertEqual(value,json.loads(encoded))

    def test_pending_is_not_overdue(self):
        for value in ['pending','To be agreed','2026-1-01','2026-10',' 2026-10-01','２０２６-10-01']:
            self.assertIn('not classified overdue',target_state(value,date(2026,10,17)))
    def test_invalid_rollover_and_leap(self):
        for value in ['2026-02-29','2026-04-31','0000-01-01','2026-13-01']:
            self.assertIn('Invalid',target_state(value,date(2026,10,17)))
        self.assertIn('Past',target_state('2024-02-29',date(2026,10,17)))
    def test_today_and_future_not_past(self):
        for value in ['2026-10-17','2026-10-18']:
            self.assertEqual('Recorded date — confirm agreement',target_state(value,date(2026,10,17)))
        self.assertEqual('Past recorded date — confirm agreement',target_state('2026-10-16',date(2026,10,17)))
    def test_missing_is_explicit(self):
        self.assertEqual('No target recorded',target_state('',date(2026,10,17)))
    def test_identity_links_and_workspace_only_clickable_sources(self):
        import json
        f=json.dumps(row_formatter('https://example.sharepoint.com/sites/ppg','/queue','/ready','/assure'), ensure_ascii=False)
        self.assertIn('FilterField1=CaseUID',f)
        self.assertIn('[$CaseUID]',f)
        self.assertIn("indexOf([$evidenceDraftLink], 'https://example.sharepoint.com/sites/ppg/') == 0",f)
        self.assertIn('Missing — no package inferred',f)
        self.assertIn('23:59:59.999+10:00',target_expression())

if __name__=='__main__':unittest.main()
