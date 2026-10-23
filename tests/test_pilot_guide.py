"""Renderer qualification uses entirely fictional supplied guide definitions."""
import unittest
from scripts.ppg_pilot_guide import render


class PilotGuide(unittest.TestCase):
    def fixture(self):
        return {'clinicalApproval': False, 'notificationsEnabled': False, 'title': 'Fictional guide', 'guideVersion': '1.0', 'asOf': 'fictional',
                'subject': 'Fictional sample', 'notice': 'Unverified <input>',
                'sections': [{'id': 'sample', 'title': 'Example', 'trigger': 'Manual',
                    'steps': ['Preserve evidence'], 'links': [{'key': 'source', 'label': 'Source'}],
                    'hold': 'Hold unknown facts'}]}

    def test_escape_and_explicit_link_binding(self):
        value = render(self.fixture(), {'source': 'https://example.invalid/?a="quoted"&b=1'})
        self.assertIn('&lt;input&gt;', value)
        self.assertIn('&quot;quoted&quot;&amp;', value)
        for binding in [{}, {'source': 'javascript:alert(1)'}]:
            with self.assertRaises(ValueError): render(self.fixture(), binding)
