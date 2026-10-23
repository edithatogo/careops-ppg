import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/lifecycle'))
from build_selected_prepared_context import build,digest,_context
from build_selected_event_routes import build as event_build
from test_selected_event_routes import fixtures,success


def fixture(kind):
    context,target,binding=fixtures();event=event_build(kind,context,target,binding)
    source=copy.deepcopy(context)
    reader=copy.deepcopy(source['properties']['definition']['actions']['Resolve_context']['actions']['Read_selected_case'])
    source['properties']['definition']['actions']['Route_preparation_check']={
        'type':'If','expression':"@and(equals(triggerBody()?['text'],'Check preparation'),equals(outputs('Selected_case_context')?['contextValid'],true))",
        'runAfter':{'Resolve_context':['Succeeded']},'actions':{'Read_prepared_file':reader},'else':{'actions':{}}}
    return event,source


class PreparedContextTests(unittest.TestCase):
    def test_both_modes_preserve_ownership_and_embed_reader_at_top_level(self):
        for kind,field,mode in [('request','text','Consultation request'),('response','text_5','Consultation response')]:
            event,source=fixture(kind);before=copy.deepcopy((event,source))
            out=build(kind,event,source,digest(source['properties']['definition']))
            self.assertEqual(success(out)['Route_ownership_event'],success(event)['Route_ownership_event'])
            self.assertNotIn('Route_unbound_consultation',success(out))
            route=out['properties']['definition']['actions']['Route_consultation_prepared_context']
            self.assertIn("triggerBody()?['"+field+"'],'"+mode+"'",route['expression'])
            self.assertEqual(route['runAfter'],{'Resolve_context':['Succeeded']})
            self.assertEqual(out['properties']['state'],'Stopped')
            self.assertEqual(before,(event,source))

    def test_stale_definition_connection_and_context_are_refused(self):
        event,source=fixture('request');approved=digest(source['properties']['definition'])
        with self.assertRaisesRegex(ValueError,'Exact reviewed'):build('request',event,source,'0'*64)
        source['properties']['connectionReferences']['shared_sharepointonline']['connectionName']='other'
        with self.assertRaisesRegex(ValueError,'connection'):build('request',event,source,approved)
        event,source=fixture('request');source['properties']['definition']['actions']['Resolve_context']['actions']['Read_selected_case']['inputs']['parameters']['dataset']='https://different.invalid'
        with self.assertRaisesRegex(ValueError,'exact selected-case'):build('request',event,source,digest(source['properties']['definition']))

    def test_writer_and_method_override_cannot_enter_prerequisite(self):
        for mutation in ('post','override','http'):
            event,source=fixture('request');action=source['properties']['definition']['actions']['Route_preparation_check']['actions']['Read_prepared_file']
            if mutation=='post':action['inputs']['parameters']['parameters/method']='POST'
            elif mutation=='override':action['inputs']['parameters']['parameters/headers']={'X-HTTP-Method':'MERGE'}
            else:action['type']='Http'
            with self.assertRaises(ValueError):build('request',event,source,digest(source['properties']['definition']))
