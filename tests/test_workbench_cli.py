import importlib.util
import json
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('workbench',Path(__file__).resolve().parents[1]/'scripts/ppg_workbench.py')
w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)

class GuidedCLI(unittest.TestCase):
    def test_draft_package_creates_editable_draft_and_preserves_edits(self):
        with tempfile.TemporaryDirectory() as tmp:
            inputs = Path(tmp) / 'inputs.json'
            output = Path(tmp) / 'draft.md'
            template = w.ROOT / 'templates/review-package.md'
            original = template.read_bytes()
            fields = re.findall(r'\{\{([A-Za-z_][A-Za-z_0-9]*)\}\}', original.decode())
            data = dict.fromkeys(fields, 'Not recorded')
            data.update(case_title='Fictional CLI case', CaseUID='fictional-cli',
                        source_snapshot='fictional-baseline', version='draft-1')
            inputs.write_text(json.dumps(data))
            arguments = ['draft-package', '--template', str(template),
                         '--inputs', str(inputs), '--output', str(output)]
            self.assertEqual(w.main(arguments), 0)
            self.assertIn('Status: DRAFT / AWAITING REVIEW', output.read_text())
            self.assertIn('Fictional CLI case', output.read_text())
            self.assertNotIn('{{', output.read_text())
            output.write_text('Retained human edit')
            self.assertNotEqual(w.main(arguments), 0)
            self.assertEqual(output.read_text(), 'Retained human edit')
            self.assertEqual(template.read_bytes(), original)
            self.assertEqual(json.loads(inputs.read_text()), data)


    def test_no_shell_and_literal_arguments(self):
        with patch.object(w.subprocess,'run',return_value=subprocess.CompletedProcess([],0)) as run:
            self.assertEqual(w.main(['lookup','--query','$(touch SHOULD_NOT_EXIST); literal']),0)
            self.assertEqual(run.call_args.args[0][-1],'$(touch SHOULD_NOT_EXIST); literal')
            self.assertFalse(run.call_args.kwargs['shell'])
    def test_failure_propagates_no_following_step(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt=Path(tmp)/'attempt.jsonl'
            with patch.object(w.subprocess,'run',return_value=subprocess.CompletedProcess([],7)) as run:
                self.assertEqual(w.main(['--receipt',str(receipt),'lookup','--help']),7)
                self.assertEqual(run.call_count,1)
            rows=[json.loads(x) for x in receipt.read_text().splitlines()]
            self.assertEqual(rows[-1]['exitCode'],7)
            self.assertEqual(receipt.stat().st_mode & 0o777,0o600)
            with patch.object(w.subprocess,'run') as run:
                self.assertEqual(w.main(['--receipt',str(receipt),'lookup','--help']),1)
                run.assert_not_called()
    def test_receipt_contains_no_private_arguments(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt=Path(tmp)/'attempt'
            with patch.object(w.subprocess,'run',return_value=subprocess.CompletedProcess([],0)):
                self.assertEqual(w.main(['--receipt',str(receipt),'lookup','PRIVATE_QUERY']),0)
            self.assertNotIn('PRIVATE_QUERY',receipt.read_text())
    def test_guide_never_executes(self):
        with patch.object(w.subprocess,'run') as run:
            self.assertEqual(w.main(['guide']),0)
            run.assert_not_called()

    def test_plan_runs_stages_and_resumes_only_after_completed_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); state=root/'run.jsonl'; plan=root/'plan.json'
            first=root/'one.txt'; second=root/'two.txt'
            original_run=subprocess.run
            plan.write_text(json.dumps({'schemaVersion':1,'steps':[
                {'step':'lookup','arguments':['literal'],'outputs':[str(first)]},
                {'step':'validate','arguments':['literal'],'outputs':[str(second)]},
            ]}))
            append=w._append_state
            def interrupt_after_first_complete(path,event):
                append(path,event)
                if event.get('event')=='completed' and event.get('index')==0:
                    raise KeyboardInterrupt()
            def command_for(step,args):
                target=first if step=='lookup' else second
                return [sys.executable,'-c','import pathlib,sys; pathlib.Path(sys.argv[1]).write_text("stage output")',str(target)]
            def make_output(cmd,**kwargs):
                result=original_run(cmd,**kwargs)
                return result
            with patch.object(w,'command',side_effect=command_for), \
                 patch.object(w.subprocess,'run',side_effect=make_output), \
                 patch.object(w,'_append_state',side_effect=interrupt_after_first_complete):
                with self.assertRaises(KeyboardInterrupt): w.run_plan(plan,state)
            with patch.object(w,'command',side_effect=command_for), \
                 patch.object(w.subprocess,'run',side_effect=make_output) as run:
                self.assertEqual(w.run_plan(plan,state,resume=True),0)
                self.assertEqual(run.call_count,1)
            events=[json.loads(x) for x in state.read_text().splitlines()]
            self.assertEqual([e['event'] for e in events].count('completed'),2)
            self.assertEqual(state.stat().st_mode & 0o777,0o600)

    def test_plan_resume_refuses_unknown_outcome_and_changed_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); state=root/'run.jsonl'; plan=root/'plan.json'; output=root/'out'
            plan.write_text(json.dumps({'schemaVersion':1,'steps':[{'step':'lookup','arguments':['literal'],'outputs':[str(output)]}]}))
            original_run=subprocess.run
            with patch.object(w,'command',return_value=[sys.executable,'-c','pass']), \
                 patch.object(w.subprocess,'run',side_effect=KeyboardInterrupt()):
                with self.assertRaises(KeyboardInterrupt): w.run_plan(plan,state)
            loaded, digest=w._load_plan(plan)
            with self.assertRaisesRegex(ValueError,'unknown outcome'):
                w._open_state(state, loaded, digest, True)

            state.unlink()
            script='import pathlib,sys; pathlib.Path(sys.argv[1]).write_text("v1")'
            with patch.object(w,'command',return_value=[sys.executable,'-c',script,str(output)]), \
                 patch.object(w.subprocess,'run',side_effect=lambda cmd,**kwargs:original_run(cmd,**kwargs)):
                self.assertEqual(w.run_plan(plan,state),0)
            output.write_text('changed')
            with self.assertRaisesRegex(ValueError,'changed or disappeared'):
                w._open_state(state, loaded, digest, True)

    def test_plan_rejects_non_allowlisted_step_and_duplicate_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan=Path(tmp)/'plan.json'
            plan.write_text(json.dumps({'schemaVersion':1,'steps':[{'step':'python','arguments':[],'outputs':['x']}]}))
            with self.assertRaisesRegex(ValueError,'Invalid step'):
                w._load_plan(plan)

    def test_plan_persists_existing_output_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); state=root/'run.jsonl'; plan=root/'plan.json'; output=root/'already-there'
            output.write_text('preserve')
            plan.write_text(json.dumps({'schemaVersion':1,'steps':[{'step':'lookup','arguments':['literal'],'outputs':[str(output)]}]}))
            with patch.object(w.subprocess,'run') as run:
                self.assertEqual(w.run_plan(plan,state),1)
                run.assert_not_called()
            events=[json.loads(x) for x in state.read_text().splitlines()]
            self.assertEqual(events[-1]['event'],'refused')
            with self.assertRaisesRegex(ValueError,'failed or was refused'):
                w._open_state(state,w._load_plan(plan)[0],w._load_plan(plan)[1],True)
            plan.write_text(json.dumps({'schemaVersion':1,'steps':[{'step':[],'arguments':[],'outputs':['x']}]}))
            with self.assertRaisesRegex(ValueError,'Invalid step'):
                w._load_plan(plan)

if __name__=='__main__': unittest.main()
