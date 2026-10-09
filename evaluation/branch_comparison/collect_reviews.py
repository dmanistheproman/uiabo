"""Combine independently completed XLSX reviews into an adjudication CSV.

Reads standard XLSX XML using Python's standard library. No Excel dependency.
It preserves both initial labels and leaves the final decision blank.
"""
import argparse
import csv
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from compare import HERE, LABELS, digest, load_cases

NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def read_sheet(path, name):
    with ZipFile(path) as archive:
        strings=[]
        if "xl/sharedStrings.xml" in archive.namelist():
            strings = [''.join(si.itertext()) for si in ET.fromstring(archive.read('xl/sharedStrings.xml')).findall('s:si', NS)]
        workbook = ET.fromstring(archive.read('xl/workbook.xml'))
        sheet = next((s for s in workbook.findall('s:sheets/s:sheet', NS) if s.attrib['name'] == name), None)
        if sheet is None:
            raise ValueError(f"Missing sheet: {name}")
        rels = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
        target = next(r.attrib['Target'] for r in rels if r.attrib['Id'] == sheet.attrib[REL])
        target = target.lstrip('/') if target.startswith('/') else 'xl/' + target
        cells={}
        for cell in ET.fromstring(archive.read(target)).findall('.//s:sheetData/s:row/s:c', NS):
            if cell.find('s:f', NS) is not None:
                raise ValueError('Review fields must contain values, not formulas')
            if cell.attrib.get('t')=='inlineStr':
                value=''.join(cell.find('s:is', NS).itertext())
            else:
                node=cell.find('s:v', NS)
                value=node.text if node is not None and node.text else ''
                if cell.attrib.get('t')=='s': value=strings[int(value)]
            cells[cell.attrib['r']]=value
        return cells


def collect(path, split, cases, dataset_hash):
    cells=read_sheet(path, split.title())
    name=cells.get('B3','').strip()
    if not name: raise ValueError('Enter the reviewer name in B3')
    if cells.get('H2') != dataset_hash: raise ValueError('Workbook dataset fingerprint does not match')
    rows={}
    for index, case in enumerate(cases, 7):
        if cells.get(f'A{index}') != case['id'] or cells.get(f'B{index}') != case['claim']:
            raise ValueError('Do not reorder/edit input claims in the workbook')
        label=cells.get(f'C{index}','').strip()
        if label and label not in LABELS: raise ValueError(f"Invalid label for {case['id']}")
        rows[case['id']]={'reviewer':name, 'label':label,
            'reason':cells.get(f'D{index}','').strip(), 'sources':cells.get(f'E{index}','').strip(),
            'reviewed_at':cells.get(f'F{index}','').strip()}
    return rows


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--a',type=Path,required=True)
    parser.add_argument('--b',type=Path,required=True)
    parser.add_argument('--split',choices=['pilot','final','regression'],required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists(): parser.error('Choose a new output path')
    dataset=HERE/'datasets'/f'{args.split}.json'
    cases=load_cases(dataset,args.split); hash_=digest(dataset)
    a=collect(args.a,args.split,cases,hash_);b=collect(args.b,args.split,cases,hash_)
    if next(iter(a.values()))['reviewer'].casefold()==next(iter(b.values()))['reviewer'].casefold():
        parser.error('Two distinct human reviewers are required')
    rows=[]
    for c in cases:
        ra,rb=a[c['id']],b[c['id']]
        row={'id':c['id'],'claim':c['claim']}
        for suffix, review in (('a',ra),('b',rb)):
            row.update({f'{key}_{suffix}' if key!='reviewer' else f'reviewer_{suffix}':review[key]
                for key in ('reviewer','label','reason','sources')})
            row[f'reviewed_at_{suffix}']=review['reviewed_at']
        row.update(final_label='',adjudicator='',decision_reason='',final_sources='',reviewed_at='',dataset_sha256=hash_)
        rows.append(row)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    print('Initial reviews preserved. Fill the final decision fields before passing this CSV to compare.py.')


if __name__=='__main__': main()
