"""Read bounded public data.gov.sg rows instead of a dataset's HTML preview.

The endpoint is fixed, no key is sent, redirects are refused, and DNS is pinned
to a public address. Dataset IDs only come from a vetted data.gov.sg URL. Rows
are never treated as evidence of an instruction, policy, or causal mechanism.
API contract: https://guide.data.gov.sg/developer-guide/dataset-apis/search-and-filter-within-dataset
"""

import asyncio
import json
import math
import re
from urllib.parse import parse_qs, urlsplit

import httpx

from .pdf_reader import public_address
from .source_policy import public_url
from .service import relevance

HOST = 'data.gov.sg'
ENDPOINT = 'https://data.gov.sg/api/action/datastore_search'
PAGE_SIZE = 100
MAX_PAGES = 2
MAX_BYTES = 1_000_000
MAX_TEXT = 5800
TIMEOUT = 10.0
ID = re.compile(r'd_[a-f0-9]{32}')


def dataset_id(url):
    try:
        parts = urlsplit(public_url(str(url)))
    except (TypeError, ValueError):
        return None
    if parts.scheme != 'https' or parts.hostname != HOST:
        return None
    path = re.fullmatch(r'/datasets/(d_[a-f0-9]{32})(?:/view)?/?', parts.path)
    if path:
        return path[1]
    if parts.path == '/api/action/datastore_search':
        values = parse_qs(parts.query).get('resource_id', [])
        if len(values) == 1 and ID.fullmatch(values[0]):
            return values[0]
    return None


async def request_page(identifier, offset):
    if not ID.fullmatch(identifier) or offset not in {0, PAGE_SIZE}:
        raise ValueError('Invalid bounded dataset request')
    address = await public_address(HOST)
    target = httpx.URL(ENDPOINT).copy_with(host=address,
        query=str(httpx.QueryParams({'resource_id': identifier, 'limit': PAGE_SIZE, 'offset': offset})).encode())
    async with httpx.AsyncClient(timeout=httpx.Timeout(6, connect=3), trust_env=False,
                                 follow_redirects=False) as client:
        async with client.stream('GET', target, headers={'Host': HOST, 'Accept': 'application/json',
                'Accept-Encoding': 'identity'}, extensions={'sni_hostname': HOST}) as response:
            if response.status_code != 200:
                raise ValueError('Public dataset request did not complete')
            if int(response.headers.get('content-length', '0')) > MAX_BYTES:
                raise ValueError('Dataset response exceeds the budget')
            data = bytearray()
            async for chunk in response.aiter_bytes():
                data.extend(chunk)
                if len(data) > MAX_BYTES:
                    raise ValueError('Dataset response exceeds the budget')
    raw = json.loads(data)
    if not isinstance(raw, dict) or raw.get('success') is not True or not isinstance(raw.get('result'), dict):
        raise ValueError('Invalid public dataset response')
    return raw['result']


def validated_page(raw):
    fields, rows = raw.get('fields'), raw.get('records')
    if (not isinstance(fields, list) or not fields or len(fields) > 120
            or not isinstance(rows, list) or len(rows) > PAGE_SIZE):
        raise ValueError('Invalid dataset fields or rows')
    names = [f.get('id') for f in fields if isinstance(f, dict)]
    if len(names) != len(fields) or any(not isinstance(n, str) or not n or len(n) > 250 for n in names):
        raise ValueError('Invalid dataset field names')
    if len(set(names)) != len(names):
        raise ValueError('Duplicate dataset fields')
    for row in rows:
        if not isinstance(row, dict) or set(row) - set(names):
            raise ValueError('Invalid dataset row schema')
        if any(isinstance(v, (dict, list)) or len(str(v)) > 2000
               or isinstance(v, float) and not math.isfinite(v) for v in row.values()):
            raise ValueError('Invalid dataset cell')
    total = raw.get('total')
    if total is not None and (isinstance(total, bool) or not isinstance(total, int) or total < len(rows)):
        raise ValueError('Invalid dataset row count')
    return names, rows, total


def table_text(identifier, names, rows, focus, *, total=None):
    """Select rows/columns without changing values or combining different rows."""
    if not rows:
        raise ValueError('Dataset contains no usable rows')
    # Preserve dimensional columns, plus explicitly requested periods or the
    # latest available period columns. Do not infer row meanings from a title.
    periods = [n for n in names if re.fullmatch(r'(?:19|20)\d{2}(?:[- /].*)?', n)]
    dimensions = [n for n in names if n not in periods and n not in {'_id'}]
    requested = set(re.findall(r'\b(?:19|20)\d{2}\b', focus))
    requested_periods = [n for n in periods if n[:4] in requested]
    periods = sorted(periods, reverse=True)
    selected_periods = list(dict.fromkeys([*requested_periods, *periods[:4]]))[:8]
    columns = [*dimensions[:24], *selected_periods]
    if not columns:
        raise ValueError('Dataset has no readable columns')

    def row_priority(row):
        label = ' '.join(str(row.get(n, '')) for n in dimensions)
        # A bounded local relevance ordering, not an interpretation of values.
        return relevance(focus, label)

    ranked = sorted(enumerate(rows), key=lambda pair: (-row_priority(pair[1]), pair[0]))
    # Many SingStat tables encode a hierarchy through indentation in a series
    # label: Male -> Accountancy, Female -> Accountancy. Reordering individual
    # rows destroys that association. Select relevant groups, retain ancestors,
    # and emit every selected row in its original order with its exact label.
    label_column = next((n for n in dimensions if any(
        isinstance(row.get(n), str) and row[n] != row[n].lstrip() for row in rows)), None)
    parents, stack = {}, []
    for index, row in enumerate(rows):
        label = str(row.get(label_column, '')) if label_column else ''
        indentation = len(label.expandtabs()) - len(label.expandtabs().lstrip())
        while stack and stack[-1][0] >= indentation:
            stack.pop()
        parents[index] = [ancestor for _, ancestor in stack]
        stack.append((indentation, index))
    chosen_indices = set()
    for index, _ in ranked:
        group = {index, *parents[index]}
        if len(chosen_indices | group) <= 40:
            chosen_indices.update(group)
    chosen = [(index, rows[index]) for index in sorted(chosen_indices)]
    def cell(value):
        if value is None:
            return '[missing]'
        return str(value).replace('|', '\\|').replace('\r', ' ').replace('\n', ' ')
    header = '| ' + ' | '.join(cell(n) for n in columns) + ' |'
    lines = [f'Public dataset {identifier}. Literal field names and row values follow.',
             'This bounded extract may omit rows or columns. Counts alone do not establish a policy instruction or cause.',
             f'Retrieved {len(rows)} rows' + (f' of {total} total rows.' if total is not None else '.'),
             header, '| ' + ' | '.join('---' for _ in columns) + ' |']
    length = sum(len(s) + 1 for s in lines)
    added = 0
    for _, row in chosen:
        line = '| ' + ' | '.join(cell(row.get(n)) for n in columns) + ' |'
        if length + len(line) + 1 > MAX_TEXT:
            break
        lines.append(line)
        length += len(line) + 1
        added += 1
    if not added:
        raise ValueError('Dataset rows exceed the text budget')
    return '\n'.join(lines)


async def read_dataset(url, focus):
    identifier = dataset_id(url)
    if identifier is None:
        raise ValueError('Not an approved public dataset URL')
    async with asyncio.timeout(TIMEOUT):
        all_rows, names, total = [], None, None
        for page in range(MAX_PAGES):
            fields, rows, reported = validated_page(await request_page(identifier, page * PAGE_SIZE))
            if names is not None and fields != names:
                raise ValueError('Dataset schema changed during pagination')
            names, total = fields, reported
            all_rows.extend(rows)
            if len(rows) < PAGE_SIZE or total is not None and len(all_rows) >= total:
                break
        return table_text(identifier, names, all_rows, focus, total=total)


def needs_catalogue_context(text):
    header = next((line for line in text.splitlines() if line.startswith('| ')), '')
    columns = [c.strip().casefold().replace(' ', '') for c in header.strip('|').split('|')]
    generic = {'dataseries','dataseriestext','series','category','sex','gender','year','month','value','count','number'}
    return bool(columns and all(c in generic or re.fullmatch(r'(?:19|20)\d{2}(?:numeric)?', c) for c in columns))


def catalogue_context(text):
    """Literal title/description/footnotes, never a generated table meaning."""
    if not isinstance(text, str):
        return ''
    heading = re.search(r'^#\s+[^#\n]+', text, re.M)
    if not heading:
        return ''
    section = text[heading.start():]
    end = re.search(r'^\s*\||^#{1,4}\s+(?:Data explorer|Sample OpenAPI|Data preview)\b', section, re.M | re.I)
    section = section[:end.start()] if end else section
    # Keep a complete paragraph/line at the boundary where possible.
    if len(section) > 1800:
        section = section[:1800].rsplit('\n',1)[0]
    return section.strip()
