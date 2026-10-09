"""Create a blinded result bundle, audit checklist and branch comparison summary."""
import argparse
import csv
import json
from pathlib import Path
import random


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=json.loads(args.report.read_text(encoding='utf-8'))
    args.output.mkdir(parents=True,exist_ok=False)
    entries=[(c,b,r) for c in report['cases'] for b,r in c['runs'].items()]
    random.SystemRandom().shuffle(entries)
    blind=[];key=[];audit=[]
    for i,(case,branch,run) in enumerate(entries,1):
        rid=f'A{i:03}'
        result=run.get('result',{})
        # Retain user-visible explanation/evidence, remove versions and diagnostic provider identity.
        blind.append({'review_id':rid,'input':case['claim'], 'outcome':run.get('outcome'),
            'error_code':run.get('error_code'), 'risk_score':result.get('misinformation_risk_score'),
            'explanation':result.get('explanation'), 'uncertainty':result.get('uncertainty'),
            'extracted_claim':result.get('extracted_claim'), 'recommended_action':result.get('recommended_action'),
            'forecast_context':result.get('forecast_context'), 'evidence':[
                {k:e.get(k) for k in ('title','url','publisher','passage','evidence_quote','stance')}
                for e in result.get('evidence',[])]})
        key.append({'review_id':rid,'case_id':case['id'],'branch':branch})
        audit.append(dict(review_id=rid,reviewer='',claim_understood='',sources_apply='',quotes_supported='',
            explanation_clear='',risk_wording_appropriate='',critical_issue='',notes=''))
    for name,data in [('blinded_results.json',blind),('PRIVATE_branch_key.json',key)]:
        (args.output/name).write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    with (args.output/'result_audit.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(audit[0]) if audit else ['review_id'])
        writer.writeheader();writer.writerows(audit)
    lines=['# Pipeline comparison', '',f"- Split: {report['split']}",f"- Run status: {report['status']}",
           f"- Cases attempted: {len(report['cases'])} / {report['planned_cases']}",
           '- Complete the citation and explanation audit before making a merge decision.', '',
           '| Metric | Original | Experimental |','| --- | ---: | ---: |']
    summary=report.get('summary',{})
    for metric in ('attempted','labelled','correct','accuracy_including_errors','macro_f1','mean_group_accuracy','wrong_decisive','errors','unresolved',
                   'decisive_precision','decisive_coverage','median_seconds','p95_seconds','http_attempts'):
        values=[summary.get(b,{}).get(metric) for b in ('original','experimental')]
        values=['Not available' if v is None else f'{v:.3f}' if isinstance(v,float) else str(v) for v in values]
        lines.append(f"| {metric.replace('_',' ')} | {values[0]} | {values[1]} |")
    lines += ['', 'HTTP attempts are diagnostic counts, not billable credits. Missing labels mean accuracy is unavailable.',
              'Keep PRIVATE_branch_key.json and the original report away from blinded reviewers until their audits are submitted.',
              'Shared wording or forecast fields can still reveal a branch; blinding is imperfect.']
    (args.output/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Summary, blinded results, audit CSV and private mapping created.')


if __name__=='__main__': main()
