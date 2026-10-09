import contextlib
import csv
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

PACK=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PACK))
import compare
import collect_reviews


class ComparisonTests(unittest.TestCase):
    def test_dataset_counts_no_cross_split_groups_or_reused_claims(self):
        groups=set();claims=set()
        for split,count in [('pilot',20),('final',60),('regression',8)]:
            cases=compare.load_cases(PACK/'datasets'/f'{split}.json',split)
            self.assertEqual(len(cases),count)
            these={c['group'] for c in cases}
            self.assertFalse(groups & these);groups.update(these)
            for c in cases:
                self.assertNotIn(c['claim'],claims);claims.add(c['claim'])
                self.assertNotIn('expected',c)
        old=json.loads((PACK.parent/'datasets/retrieval_seed_v1.json').read_text(encoding='utf-8'))
        reserved={c['claim'].casefold() for s in ('pilot','final') for c in compare.load_cases(PACK/'datasets'/f'{s}.json',s)}
        self.assertFalse(reserved & {c['claim'].casefold() for c in old['cases']})

    def test_labels_and_sources_are_not_sent_to_workers(self):
        payload=compare.worker_payload({'claim':'Test claim','expected':'supported','reference_urls':['https://hidden.example'],'reviewer':'secret'},'2026-09-29T01:00:00Z',None)
        self.assertEqual(set(payload),{'claim','assessed_at','forecast_fixture'})

    def test_forecast_conflict_is_distinct_from_false(self):
        self.assertEqual(compare.outcome({'assessment_outcome':'highly_unlikely','misinformation_risk_score':85}),'unresolved')
        self.assertEqual(compare.outcome({'assessment_outcome':'contradicted','forecast_context':{'risk_basis':'forecast_comparison'}}),'forecast_conflict')
        self.assertEqual(compare.outcome({'assessment_outcome':'contradicted'}),'contradicted')
        self.assertEqual(compare.outcome({'assessment_outcome':'unsupported','misinformation_risk_score':50}),'unresolved')
        with self.assertRaises(ValueError): compare.outcome({'misinformation_risk_score':95})

    def test_errors_stay_in_accuracy_denominator_and_group_weighting(self):
        cases=[];labels={}
        for i,(gold,pred,group) in enumerate([('supported','supported','a'),('contradicted','supported','a'),('unresolved',None,'b')]):
            cid=str(i); labels[cid]={'final_label':gold}
            run={'outcome':pred,'duration_seconds':i+1} if pred else {'error_code':'TIMEOUT','duration_seconds':3}
            cases.append({'id':cid,'group':group,'topic':'test','runs':{'original':run,'experimental':run}})
        result=compare.summarise(cases,labels)['original']
        self.assertAlmostEqual(result['accuracy_including_errors'],1/3)
        self.assertEqual(result['errors'],1)
        self.assertEqual(result['wrong_decisive'],1)
        self.assertEqual(result['decisive_precision'],.5)
        self.assertEqual(result['mean_group_accuracy'],.25)
        self.assertEqual(result['confusion']['unresolved']['error'],1)

    def test_no_labels_no_invented_accuracy(self):
        result=compare.summarise([],{})
        self.assertIsNone(result['original']['accuracy_including_errors'])
        self.assertIsNone(result['original']['macro_f1'])

    def test_label_gate_checks_independence_fingerprint_sources_and_completeness(self):
        case={'id':'T1'}
        row=dict(id='T1',reviewer_a='Alice',reviewer_b='Bob',label_a='supported',label_b='supported',
            reason_a='Exact evidence',reason_b='Exact evidence',sources_a='https://a.example',sources_b='https://b.example',
            final_label='supported',adjudicator='Chris',decision_reason='Confirmed scope',final_sources='https://a.example',
            reviewed_at='2026-09-29',dataset_sha256='abc')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'labels.csv'
            def write(value):
                with path.open('w',newline='',encoding='utf-8') as stream:
                    w=csv.DictWriter(stream,fieldnames=list(value));w.writeheader();w.writerow(value)
            write(row);self.assertEqual(compare.load_labels(path,[case],'abc')['T1']['final_label'],'supported')
            for changes in [{'reviewer_b':'Alice'},{'dataset_sha256':'wrong'},{'final_sources':''},{'reason_b':''},{'final_label':'fake'}]:
                write(row|changes)
                with self.assertRaises(ValueError):compare.load_labels(path,[case],'abc')

    def test_unreviewed_final_cannot_execute_or_partial_run(self):
        tree={'root':'unused','python':sys.executable}
        with patch.object(compare,'fingerprint',return_value=tree),patch.object(compare,'run_worker') as run:
            for args in [['--split','final','--execute'],['--split','final','--limit','1','--execute']]:
                with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):compare.main(args)
            run.assert_not_called()

    def test_finished_workbooks_have_every_claim_and_no_labels(self):
        for reviewer in ('A','B'):
            path=PACK/'outputs/review_pack_20260929'/f'Reviewer_{reviewer}.xlsx'
            for split in ('pilot','final','regression'):
                cells=collect_reviews.read_sheet(path,split.title())
                dataset=PACK/'datasets'/f'{split}.json'
                self.assertEqual(cells['H2'],compare.digest(dataset))
                for n,case in enumerate(compare.load_cases(dataset,split),7):
                    self.assertEqual(cells[f'A{n}'],case['id'])
                    self.assertEqual(cells[f'B{n}'],case['claim'])
                    self.assertFalse(cells.get(f'C{n}'))

    def test_review_collection_rejects_changed_claims_and_invalid_labels(self):
        case={'id':'P01','claim':'Input'}
        cells={'B3':'Alice','H2':'abc','A7':'P01','B7':'Input','C7':'supported','D7':'Reason','E7':'https://e.example','F7':'2026-09-29'}
        with patch.object(collect_reviews,'read_sheet',return_value=cells):
            result=collect_reviews.collect('unused','pilot',[case],'abc')
            self.assertEqual(result['P01']['label'],'supported')
            cells['B7']='Changed claim'
            with self.assertRaises(ValueError):collect_reviews.collect('unused','pilot',[case],'abc')

    def test_worker_timeout_is_an_error_not_a_verdict(self):
        with patch('subprocess.run',side_effect=subprocess.TimeoutExpired('worker',1)):
            result=compare.run_worker({'python':sys.executable,'root':str(PACK.parents[1])},'original',{},PACK/'none',30)
        self.assertEqual(result['error_code'],'WORKER_TIMEOUT')
        self.assertNotIn('outcome',result)

    def test_coordinator_alternates_branches_checkpoints_and_refuses_overwrite(self):
        original={'root':'original-test','python':sys.executable,'source_sha256':'old'}
        experimental={'root':'experimental-test','python':sys.executable,'source_sha256':'new'}
        order=[]
        def fake_worker(tree,branch,payload,credentials,timeout):
            if payload.get('preflight'):return {'ready':True,'requests':[]}
            order.append(branch)
            self.assertEqual(set(payload),{'claim','assessed_at','forecast_fixture'})
            return {'outcome':'supported','duration_seconds':1,'requests':[],
                'result':{'misinformation_risk_score':3,'explanation':'SIMULATED OUTPUT, NOT A LIVE EVALUATION','evidence':[]}}
        with tempfile.TemporaryDirectory() as tmp:
            report=Path(tmp)/'report.json';creds=Path(tmp)/'.env';creds.touch()
            args=['--split','pilot','--limit','2','--execute','--pause','0','--credentials',str(creds),'--report',str(report)]
            with patch.object(compare,'fingerprint',side_effect=lambda root: original if str(root) in ('C:\\Dev\\uiabo','original-test') else experimental),\
                 patch.object(compare,'run_worker',side_effect=fake_worker),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(compare.main(args),0)
                saved=json.loads(report.read_text(encoding='utf-8'))
                self.assertEqual(saved['status'],'complete')
                self.assertEqual(order,['original','experimental','experimental','original'])
                self.assertIsNone(saved['summary']['original']['accuracy_including_errors'])
                before=report.read_bytes()
                with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):compare.main(args)
                self.assertEqual(report.read_bytes(),before)
            proc=subprocess.run([sys.executable,'-B',str(PACK/'review_results.py'),str(report),'--output',str(Path(tmp)/'review')],
                capture_output=True,text=True,timeout=20)
            self.assertEqual(proc.returncode,0,proc.stderr)
            blind=json.loads((Path(tmp)/'review/blinded_results.json').read_text(encoding='utf-8'))
            self.assertEqual(len(blind),4)
            self.assertEqual(blind[0]['risk_score'],3)
            self.assertNotIn('branch',blind[0])
            self.assertEqual(len(json.loads((Path(tmp)/'review/PRIVATE_branch_key.json').read_text())),4)

    def test_real_branches_assemble_results_offline_without_firebase(self):
        for branch,root in [('original',Path('C:/Dev/uiabo')),('experimental',PACK.parents[1])]:
            if not root.is_dir(): self.skipTest('Local original tree unavailable')
            tree=compare.fingerprint(root)
            proc=subprocess.run([tree['python'],'-B',str(PACK/'tests/offline_branch_probe.py'),str(root/'backend'),branch],
                capture_output=True,text=True,timeout=30)
            self.assertEqual(proc.returncode,0,proc.stderr)
            self.assertEqual(json.loads(proc.stdout)['network_requests'],0)


if __name__=='__main__':unittest.main()
