"""Create editable draw.io infographic pages and matching SVG/PNG slide assets.

Requires Pillow for text measurement; PyMuPDF is optional for PNG rendering.
Run in this directory to regenerate. Back up manual draw.io edits first.
"""
from pathlib import Path
from html import escape
import json
import xml.etree.ElementTree as ET
from PIL import ImageFont

ROOT = Path(__file__).resolve().parent
W, H = 1920, 1080
INK, MUTED, TEAL, BLUE, PAPER = '#15374A', '#536D7C', '#007F87', '#2465A7', '#F3F7FA'
FONT = Path('C:/Windows/Fonts/arial.ttf')
BOLD = Path('C:/Windows/Fonts/arialbd.ttf')
CHECKS = []


def font(size, bold=False):
    return ImageFont.truetype(str(BOLD if bold else FONT), size)


def wrap(value, width, size, bold=False):
    output = []
    for paragraph in value.split('\n'):
        line = ''
        for word in paragraph.split():
            trial = (line + ' ' + word).strip()
            if line and font(size, bold).getlength(trial) > width:
                output.append(line); line = word
            else:
                line = trial
        output.append(line)
    return output


class Page:
    def __init__(self, mxfile, name, ident):
        diagram = ET.SubElement(mxfile, 'diagram', id=ident, name=name)
        model = ET.SubElement(diagram, 'mxGraphModel', dx=str(W), dy=str(H), grid='1', gridSize='10',
            guides='1', tooltips='1', connect='1', arrows='1', fold='1', page='1', pageScale='1',
            pageWidth=str(W), pageHeight=str(H), background=PAPER, math='0', shadow='0')
        self.root = ET.SubElement(model, 'root')
        ET.SubElement(self.root, 'mxCell', id='0')
        ET.SubElement(self.root, 'mxCell', id='1', parent='0')
        self.name, self.ident, self.n = name, ident, 0
        self.groups = {'1': (0, 0)}
        self.svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="title desc">',
            f'<title id="title">{escape(name)}</title>',
            '<desc id="desc">UIABO implemented text-checking prototype: processing stages, API roles and evidence-based result handling. September 2026.</desc>',
            f'<rect width="{W}" height="{H}" fill="{PAPER}"/>']

    def cell(self, value, style, x, y, w, h, parent='1', ident=None):
        self.n += 1
        ident = ident or f'{self.ident}-{self.n}'
        node = ET.SubElement(self.root, 'mxCell', id=ident, value=value, style=style, vertex='1', parent=parent)
        ox, oy = self.groups.get(parent, (0, 0))
        ET.SubElement(node, 'mxGeometry', x=str(x-ox), y=str(y-oy), width=str(w), height=str(h), attrib={'as': 'geometry'})
        assert x >= 0 and y >= 0 and x+w <= W and y+h <= H, (ident, x, y, w, h)
        return ident

    def group(self, ident, x, y, w, h):
        self.cell('', 'group;', x, y, w, h, ident=ident)
        self.groups[ident] = (x, y)
        return ident

    def box(self, x, y, w, h, fill='white', stroke='none', radius=16, parent='1', ident=None):
        style = f'rounded={int(radius > 0)};absoluteArcSize=1;arcSize={radius*2};html=1;fillColor={fill};strokeColor={stroke};strokeWidth=1;'
        ident = self.cell('', style, x, y, w, h, parent, ident)
        self.svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}"/>')
        return ident

    def text(self, value, x, y, w, size=20, colour=INK, bold=False, lh=None, parent='1', align='left', max_h=None):
        lh = lh or round(size*1.35)
        lines = wrap(value, w, size, bold)
        height = len(lines)*lh
        if max_h is not None:
            assert height <= max_h, ('text height', value, height, max_h)
        for line in lines:
            assert font(size, bold).getlength(line) <= w + .5, ('text width', line, w)
        html = f'<div style="font-family:Arial;font-size:{size}px;line-height:{lh}px;text-align:{align};">' + '<br>'.join(escape(line) for line in lines) + '</div>'
        self.cell(html, f'text;html=1;whiteSpace=wrap;overflow=visible;strokeColor=none;fillColor=none;align={align};verticalAlign=top;spacing=0;fontFamily=Arial;fontSize={size};fontStyle={int(bold)};fontColor={colour};', x,y,w,height,parent)
        tx = x+w/2 if align == 'center' else x
        anchor = 'middle' if align == 'center' else 'start'
        for i, line in enumerate(lines):
            self.svg.append(f'<text x="{tx}" y="{y+i*lh+size}" font-family="Arial,Helvetica,sans-serif" font-size="{size}" font-weight="{700 if bold else 400}" fill="{colour}" text-anchor="{anchor}">{escape(line)}</text>')
        CHECKS.append({'page':self.name,'text':value,'lines':len(lines),'height':height})

    def circle(self, x,y,d,fill, parent='1'):
        self.cell('',f'ellipse;html=1;fillColor={fill};strokeColor=none;',x,y,d,d,parent)
        self.svg.append(f'<circle cx="{x+d/2}" cy="{y+d/2}" r="{d/2}" fill="{fill}"/>')

    def arrow(self, source, target, x1,y1,x2,y2):
        self.n += 1
        node = ET.SubElement(self.root,'mxCell',id=f'{self.ident}-edge-{self.n}', value='',
            style='edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;strokeColor=#719BAE;strokeWidth=2;endArrow=block;endFill=1;exitX=1;exitY=0.5;entryX=0;entryY=0.5;',
            edge='1',parent='1',source=source,target=target)
        ET.SubElement(node,'mxGeometry',relative='1',attrib={'as':'geometry'})
        self.svg.append(f'<path d="M{x1} {y1} H{x2-6}" fill="none" stroke="#719BAE" stroke-width="2"/>')
        self.svg.append(f'<path d="M{x2-8} {y2-5} L{x2} {y2} L{x2-8} {y2+5} Z" fill="#719BAE"/>')

    def header(self, title, subtitle, page_number):
        self.box(0,0,W,188,INK,radius=0)
        self.text('uiabo.',64,25,260,size=36,bold=True,colour='white')
        self.text('IMPLEMENTED TEXT PROTOTYPE  /  SEPTEMBER 2026',1100,40,756,size=18,colour='#B4DDE4',align='center')
        self.text(title,64,82,1792,size=46,bold=True,colour='white')
        self.text(subtitle,64,145,1792,size=22,colour='#C6DBE5')
        self.text(f'UIABO  /  FINAL YEAR PROJECT                                         {page_number} / 02',64,1035,1792,size=16,colour=MUTED)

    def save(self, stem):
        svg = '\n'.join(self.svg+['</svg>'])
        (ROOT/f'{stem}.svg').write_text(svg,encoding='utf-8')
        import fitz
        doc = fitz.open(stream=svg.encode(),filetype='svg')
        doc[0].get_pixmap(matrix=fitz.Matrix(2,2),alpha=False).save(str(ROOT/f'{stem}.png'))
        doc.close()


def build():
    mx = ET.Element('mxfile',host='app.diagrams.net',type='device',compressed='false')
    p=Page(mx,'01 - Pipeline overview','uiabo-pipeline')
    p.header('From message to evidence', 'How UIABO checks a short text claim and explains what the evidence supports.',1)
    p.text('ONE CHECK, SIX STEPS',64,215,850,size=18,bold=True,colour=TEAL)
    p.text('The main route below continues when a factual claim is identified.',950,215,906,size=19,colour=MUTED,align='center')
    stages=[
        ('Submit &\nprepare','Paste English text.\nCheck account and allowance.\nValidate and normalise the input.','App + FastAPI','Validated text',BLUE,'#E8F0FC'),
        ('Identify\nthe claim','3 models classify the text.\n2 agreeing votes needed.\nExtract one factual claim.','Ollama Cloud','Checkable claim','#6650A2','#F1ECFA'),
        ('Find\nsources','Look for published fact checks and official sources.\nBroaden weak searches.','Google + Tavily','Source candidates',TEAL,'#E4F4F1'),
        ('Read &\nfilter evidence','Read the original pages.\nCheck source eligibility, relevance and policy scope.','Tavily + Ollama','Quoted passages',TEAL,'#E4F4F1'),
        ('Assess\nthe claim','Compare facts, amounts, dates and affected people.\nCombine evidence stances.','Ollama + rules','Grounded assessment','#6650A2','#F1ECFA'),
        ('Explain\n& save','Show the result, sources and uncertainty.\nSave history and update the allowance atomically.','App + Firestore','Saved result',BLUE,'#E8F0FC'),
    ]
    for i,(title,body,api,output,accent,tint) in enumerate(stages):
        x,y=64+i*304,258
        g=p.group(f'stage-{i+1}',x,y,272,410)
        p.box(x,y+5,272,405,'#E2EAF0',radius=18,parent=g)
        p.box(x,y,272,405,'white','#D9E4EA',18,parent=g)
        p.circle(x+20,y+20,40,accent,parent=g)
        p.text(f'{i+1:02d}',x+20,y+24,40,size=21,bold=True,colour='white',align='center',parent=g)
        p.text(title,x+20,y+78,232,size=28,bold=True,lh=33,parent=g,max_h=66)
        p.text(body,x+20,y+164,232,size=20,lh=27,parent=g,max_h=162)
        p.box(x+16,y+337,240,38,tint,radius=10,parent=g)
        p.text(api,x+20,y+344,232,size=18,bold=True,colour=accent,align='center',parent=g,max_h=27)
        p.text(output.upper(),x+20,y+385,232,size=13,bold=True,colour=MUTED,parent=g,max_h=20)
    for i in range(5):
        p.arrow(f'stage-{i+1}',f'stage-{i+2}',64+i*304+272,463,64+(i+1)*304,463)
    p.box(64,695,1792,68,'#E2EEF5',radius=14)
    p.text('DATE CONTEXT',84,708,195,size=17,bold=True,colour=BLUE)
    p.text('“From October” → assume the current year, show the assumption, and let the user correct it.',287,712,1535,size=22,colour=INK)
    p.text('THE SERVICES BEHIND THE CHECK',64,790,1792,size=18,bold=True,colour=TEAL)
    providers=[('Firebase Auth','Sign-in + verified identity'),('Ollama Cloud','Classification + AI reasoning'),('Google Fact Check','Published fact-check discovery'),('Tavily','Web search + page extraction'),('Cloud Firestore','Private history + allowances')]
    for i,(name,role) in enumerate(providers):
        x=64+i*364
        p.box(x,827,336,89,'white','#D9E4EA',12)
        p.text(name,x+18,839,300,size=23,bold=True,max_h=32)
        p.text(role,x+18,878,300,size=17,colour=MUTED,max_h=24)
    p.box(64,940,1792,73,INK,radius=14)
    notes=[('NON-FACTUAL TEXT','Return a saved explanation; skip evidence search.'),('NO USEFUL EVIDENCE','Explain uncertainty; missing evidence is not proof of falsity.'),('TECHNICAL FAILURE','Return an error; a failed check uses no allowance.')]
    for i,(title,body) in enumerate(notes):
        x=84+i*596
        p.text(title,x,951,554,size=15,bold=True,colour='#82DDD5')
        p.text(body,x,977,554,size=16,colour='white',max_h=23)
    p.save('UIABO_Pipeline_Infographic')

    p=Page(mx,'02 - APIs and model roles','uiabo-api-map')
    p.header('Which API does what?', 'POST /analysis/text sends the claim to FastAPI, which coordinates the external services below.',2)
    p.text('SERVICE',84,213,288,size=17,bold=True,colour=TEAL)
    p.text('ROLE IN UIABO',422,213,474,size=17,bold=True,colour=TEAL)
    p.text('INTERFACE USED',934,213,426,size=17,bold=True,colour=TEAL)
    p.text('MODELS / KEY DETAIL',1434,213,398,size=17,bold=True,colour=TEAL)
    rows=[
        ('Firebase\nAuthentication','ACCESS',BLUE,'#E8F0FC',
         'Sign in and identify the user.\nBackend verifies the ID token\nand email-verification status.',
         'Firebase JS SDK in the app\nFirebase Admin SDK on backend',
         'Controls account access.\nDoes not decide whether\na claim is true.'),
        ('Ollama Cloud','STEPS 02–05','#6650A2','#F1ECFA',
         '3 models vote on the category.\nGemma extracts + expands queries.\nGPT-OSS selects + assesses evidence.',
         'POST ollama.com/api/chat\nHTTPS model inference',
         'gpt-oss:120b\ngemma4:31b\nnemotron-3-super'),
        ('Google\nFact Check Tools','STEP 03',TEAL,'#E4F4F1',
         'Find existing published fact checks.\nUse review links to discover\noriginal evidence pages.',
         'GET factchecktools.googleapis.com\n/v1alpha1/claims:search',
         'Discovery only. An empty\nmatch does not mean the\nclaim is false.'),
        ('Tavily','STEPS 03–04',TEAL,'#E4F4F1',
         'Search preferred and wider sources.\nExtract original page text for\npassage selection and assessment.',
         'POST api.tavily.com/search\nPOST api.tavily.com/extract',
         'Search snippets are leads.\nExtracted, validated passages\nare used as evidence.'),
        ('Cloud Firestore','STEP 06',BLUE,'#E8F0FC',
         'Save user-owned results and sources.\nCommit the completed result and\nallowance update together.',
         'Firestore Python client\nBackend transaction + history APIs',
         'Private result history.\nReplaying the same request\ndoes not charge twice.'),
    ]
    for i,(name,step,accent,tint,role,endpoint,note) in enumerate(rows):
        x,y=64,248+i*138
        g=p.group(f'provider-{i+1}',x,y,1792,122)
        p.box(x,y,1792,122,'white','#D9E4EA',14,parent=g)
        p.box(x,y,320,122,tint,radius=14,parent=g)
        p.text(step,x+20,y+12,280,size=13,bold=True,colour=accent,parent=g)
        p.text(name,x+20,y+38,280,size=24,bold=True,lh=29,parent=g,max_h=62)
        p.text(role,422,y+20,474,size=20,lh=27,parent=g,max_h=90)
        p.text(endpoint,934,y+28,426,size=18,lh=29,parent=g,max_h=87)
        p.text(note,1434,y+20,398,size=20,lh=27,parent=g,max_h=90)
    p.box(64,952,1792,63,INK,radius=14)
    p.text('VOTING ≠ TRUTH VERDICT',84,965,365,size=17,bold=True,colour='#82DDD5')
    p.text('Voting chooses the claim category. The final assessment compares evidence and combines its stances.',467,966,1368,size=20,colour='white')
    p.save('UIABO_Pipeline_API_Map')
    ET.indent(mx,space='  ')
    ET.ElementTree(mx).write(ROOT/'UIABO_Pipeline_Infographic.drawio',encoding='utf-8',xml_declaration=True)
    (ROOT/'PIPELINE_INFOGRAPHIC_VALIDATION.json').write_text(json.dumps({'pages':2,'page_size':[W,H],'png_size':[W*2,H*2], 'editable_text_blocks':len(CHECKS),'text_bounds_checked':True,'checks':CHECKS},indent=2),encoding='utf-8')
    print(f'Generated editable two-page draw.io + SVG/PNG exports; {len(CHECKS)} text blocks checked.')


if __name__ == '__main__':
    build()
