"""Generate an editable draw.io functionality WBS and matching slide-ready SVG."""
from pathlib import Path
import xml.etree.ElementTree as ET
from html import escape

ROOT = Path(__file__).resolve().parent
WIDTH, HEIGHT = 1920, 1080
MODULES = [
    ('Account access', 'Individual users', [
        ('W', ['Free registration', '& email verification']),
        ('W', ['Sign in / out', '& password reset']),
        ('W', ['View profile', '& edit name']),
        ('W', ['In-app Help']),
        ('P', ['Delete account']),
    ]),
    ('Content checking', 'Free / Premium', [
        ('W', ['Submit & validate', 'English text']),
        ('W', ['Extract claim; retrieve', '& assess evidence']),
        ('P', ['Webpage analysis', '& malicious-link check']),
        ('P', ['Premium images:', 'caption & OCR correction']),
        ('P', ['Premium: image context', '& deepfake (required)']),
    ]),
    ('Results & evidence', 'Individual users', [
        ('W', ['Concern, risk indicator', '& uncertainty']),
        ('W', ['Explanation, passages', '& source links']),
        ('W', ['View & reopen', 'private result history']),
        ('W', ['Share summary text', '& citation URLs']),
        ('P', ['Delete history &', 'public result links']),
    ]),
    ('Allowances & plans', 'Free / Premium', [
        ('W', ['Free allowance:', '1 successful check/day']),
        ('W', ['Premium allowance:', '60 checks/month']),
        ('W', ['Display / refresh', 'remaining allowance']),
        ('P', ['Paid upgrade, renewal', '& cancellation']),
    ]),
    ('Feedback & admin', 'Users / System administrator', [
        ('P', ['Report incorrect', 'analysis results']),
        ('P', ['Submit a service review']),
        ('P', ['Admin access;', 'query & view accounts']),
        ('P', ['Create operational users;', 'suspend / restore access']),
        ('P', ['Review user feedback']),
    ]),
    ('Data engineering', 'Data Engineer portal', [
        ('P', ['Portal access', '& profile management']),
        ('P', ['Incorrect-results', 'dashboard']),
        ('P', ['Investigate reported', 'incorrect results']),
        ('P', ['Monitor data-ingestion', 'pipelines']),
    ]),
]
COLOURS = {
    'W': ('#E9F6F1', '#55A98B', '#176C50', 'WORKING'),
    'P': ('#FFF5E7', '#D1A45D', '#8A5C15', 'PLANNED'),
}


def build():
    mx = ET.Element('mxfile', host='app.diagrams.net', type='device', compressed='false')
    page = ET.SubElement(mx, 'diagram', id='uiabo-functionality-wbs', name='Functionality WBS — slide overview')
    model = ET.SubElement(page, 'mxGraphModel', dx=str(WIDTH), dy=str(HEIGHT), grid='1', gridSize='10',
                          guides='1', tooltips='1', connect='1', arrows='1', fold='1', page='1',
                          pageScale='1', pageWidth=str(WIDTH), pageHeight=str(HEIGHT), background='#FFFFFF', math='0', shadow='0')
    graph = ET.SubElement(model, 'root')
    ET.SubElement(graph, 'mxCell', id='0'); ET.SubElement(graph, 'mxCell', id='1', parent='0')
    edges, shapes = [], []
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="title desc">',
           '<title id="title">UIABO overall product hierarchy — functionality WBS</title>',
           '<desc id="desc">Six modules with working prototype functions in green and planned functions in amber. This is a functional decomposition, not a process flow or schedule.</desc>',
           '<rect width="1920" height="1080" fill="white"/>']

    def label(ident, value, x, y, w, h, size=20, colour='#183B50', bold=False, align='left'):
        cell = ET.SubElement(graph, 'mxCell', id=ident, value=value,
                             style=f'text;html=1;whiteSpace=wrap;strokeColor=none;fillColor=none;align={align};verticalAlign=middle;fontFamily=Arial;fontSize={size};fontColor={colour};fontStyle={int(bold)};', vertex='1', parent='1')
        ET.SubElement(cell, 'mxGeometry', x=str(x), y=str(y), width=str(w), height=str(h), attrib={'as':'geometry'})
        anchor = 'middle' if align == 'center' else 'start'
        sx = x+w/2 if align == 'center' else x
        shapes.append(f'<text x="{sx}" y="{y+h/2}" dominant-baseline="middle" text-anchor="{anchor}" font-family="Arial, sans-serif" font-size="{size}" font-weight="{700 if bold else 400}" fill="{colour}">{escape(value)}</text>')

    def box(ident, lines, x, y, w, h, fill, stroke, text_colour, tag=None, subtitle=None, dashed=False, size=21):
        if tag:
            content = f'<div style="font-family:Arial;text-align:left;line-height:1.2"><div style="font-size:14px;font-weight:bold;color:{text_colour};margin-bottom:7px">{escape(tag)}</div>'
            content += '<div style="font-size:20px;color:#203B4A">' + '<br>'.join(escape(line) for line in lines) + '</div></div>'
        else:
            content = f'<div style="font-family:Arial;text-align:center;line-height:1.2;font-weight:bold;font-size:{size}px">' + '<br>'.join(escape(line) for line in lines) + '</div>'
            if subtitle: content += f'<div style="font-family:Arial;font-size:14px;text-align:center;margin-top:9px">{escape(subtitle)}</div>'
        style = f'rounded=1;arcSize=12;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};strokeWidth=1.5;fontColor={text_colour};fontFamily=Arial;fontSize={size};align={"left" if tag else "center"};verticalAlign=middle;spacing=14;'
        if dashed: style += 'dashed=1;dashPattern=5 3;'
        cell = ET.SubElement(graph, 'mxCell', id=ident, value=content, style=style, vertex='1', parent='1')
        ET.SubElement(cell, 'mxGeometry', x=str(x), y=str(y), width=str(w), height=str(h), attrib={'as':'geometry'})
        dash = ' stroke-dasharray="7 4"' if dashed else ''
        shapes.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{fill}" stroke="{stroke}" stroke-width="1.5"{dash}/>')
        if tag:
            shapes.append(f'<text x="{x+14}" y="{y+25}" font-family="Arial, sans-serif" font-size="14" font-weight="700" fill="{text_colour}">{escape(tag)}</text>')
            for i, line in enumerate(lines):
                shapes.append(f'<text x="{x+14}" y="{y+53+i*25}" font-family="Arial, sans-serif" font-size="20" fill="#203B4A">{escape(line)}</text>')
        else:
            for i, line in enumerate(lines):
                shapes.append(f'<text x="{x+w/2}" y="{y+34+i*26}" text-anchor="middle" font-family="Arial, sans-serif" font-size="{size}" font-weight="700" fill="{text_colour}">{escape(line)}</text>')
            if subtitle:
                shapes.append(f'<text x="{x+w/2}" y="{y+h-18}" text-anchor="middle" font-family="Arial, sans-serif" font-size="14" fill="{text_colour}">{escape(subtitle)}</text>')

    def edge(ident, source, target, points, child=False):
        style = 'edgeStyle=none;rounded=0;html=1;strokeColor=#9BAEB7;strokeWidth=1.5;endArrow=none;startArrow=none;exitX=0.5;exitY=1;exitDx=0;exitDy=0;'
        style += 'entryX=0;entryY=0.5;' if child else 'entryX=0.5;entryY=0;'
        cell = ET.SubElement(graph, 'mxCell', id=ident, value='', style=style, edge='1', parent='1', source=source, target=target)
        geo = ET.SubElement(cell, 'mxGeometry', relative='1', attrib={'as':'geometry'})
        mids = ET.SubElement(geo, 'Array', attrib={'as':'points'})
        for x, y in points[1:-1]: ET.SubElement(mids, 'mxPoint', x=str(x), y=str(y))
        edges.append('<polyline points="'+' '.join(f'{x},{y}' for x,y in points)+'" fill="none" stroke="#9BAEB7" stroke-width="1.5"/>')

    label('heading', 'UIABO overall product hierarchy', 45, 26, 1400, 48, size=34, bold=True)
    label('subtitle', 'Functionality work breakdown structure', 45, 78, 1400, 30, size=20, colour='#5B7380')
    label('date', 'Prototype status · 8 September 2026', 1445, 35, 430, 30, size=17, align='center', colour='#5B7380')
    box('product', ['uiabo'], 750, 135, 420, 82, '#123D55', '#123D55', '#FFFFFF', subtitle='AI misinformation detection for short-form content', size=29)
    for index, (name, role, leaves) in enumerate(MODULES, 1):
        x = 45 + (index-1)*310
        module = f'module-{index}'
        box(module, [f'{index}. {name}'], x, 285, 280, 83, '#1F526A', '#1F526A', '#FFFFFF', subtitle=role, size=21)
        edge(f'root-edge-{index}', 'product', module, [(960,217),(960,250),(x+140,250),(x+140,285)])
        for n, (status, lines) in enumerate(leaves, 1):
            y = 405 + (n-1)*106
            ident = f'function-{index}-{n}'
            fill, stroke, ink, tag = COLOURS[status]
            box(ident, lines, x+22, y, 258, 92, fill, stroke, ink, tag=f'{index}.{n}  {tag}', dashed=status=='P')
            edge(f'child-edge-{index}-{n}', module, ident,
                 [(x+140,368),(x+140,386),(x+7,386),(x+7,y+46),(x+22,y+46)], child=True)

    # These are editable text/shape nodes in draw.io too.
    label('legend-working', 'WORKING  — implemented in the text prototype', 45, 959, 780, 28, size=19, bold=True, colour='#176C50')
    label('legend-planned', 'PLANNED  — product scope; not yet implemented', 920, 959, 910, 28, size=19, bold=True, colour='#8A5C15')
    label('scope-note', 'Deepfake applies to static images and remains required. Audio and video are excluded. Premium allowance is active; paid billing is not.', 45, 1000, 1830, 25, size=17, colour='#516B78')
    label('evidence-note', 'Working indicates available functionality, not validated detection accuracy. Source: UIABO PTD §§7.1–7.5 and URS §2.2.', 45, 1030, 1830, 25, size=17, colour='#516B78')
    svg += edges + shapes + ['</svg>']
    ET.indent(mx, space='  ')
    path = ROOT/'UIABO_Functionality_WBS.drawio'
    ET.ElementTree(mx).write(path, encoding='utf-8', xml_declaration=True)
    (ROOT/'UIABO_Functionality_WBS.svg').write_text('\n'.join(svg), encoding='utf-8')
    print(f'Created {path.name} and SVG preview: {len(MODULES)} modules, {sum(len(m[2]) for m in MODULES)} function groups.')


if __name__ == '__main__':
    build()
