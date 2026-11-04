"""Bind two numeric observations to Markdown table cells, without guessing.

None means there is no table and the existing prose checks should apply. False
means a table exists but its labels cannot establish the requested association.
This is deliberately bounded and conservative, not a general spreadsheet parser.
"""

from decimal import Decimal, InvalidOperation
import re


STOP = {'a', 'an', 'the', 'of', 'for', 'in', 'by', 'and', 'to', 'at'}
VALUE_HEADERS = {'value', 'values', 'number', 'count', 'amount', 'total', 'observation', 'numeric'}
PERIOD_HEADERS = {'year', 'period', 'date', 'month', 'quarter', 'time'}
UNIT_WORDS = {
    'percent': {'percent', 'percentage', 'pct'},
    'people': {'people', 'persons', 'person'},
    'currency': {'currency', 'dollars', 'dollar', 'sgd', 'usd', 'eur', 'gbp'},
    'other': set(),
}


def words(text):
    return set(re.findall(r'[a-z0-9]+', str(text).casefold())) - STOP


def label_in(label, text):
    wanted = words(label)
    return bool(wanted) and wanted <= words(text)


def cells(line):
    line = line.strip()
    if line.startswith('|'):
        line = line[1:]
    if line.endswith('|') and not line.endswith('\\|'):
        line = line[:-1]
    return [value.replace('\\|', '|') for value in re.split(r'(?<!\\)\|', line)]


def number(cell):
    value = re.sub(r'[*_`]', '', cell).strip()
    match = re.fullmatch(r'(?:[A-Z]{0,3}\s*[$\u20ac\u00a3]\s*)?'
                         r'(-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*(%)?', value)
    if not match:
        return None
    try:
        return Decimal(match[1].replace(',', ''))
    except InvalidOperation:
        return None


def period_in(period, cell):
    required = words(period)
    return bool(required) and required <= words(cell)


def tables(passage):
    lines = passage.splitlines()
    found, last_end = [], 0
    index = 1
    while index < len(lines):
        delimiter = cells(lines[index])
        if ('|' not in lines[index] or len(delimiter) < 2
                or not all(re.fullmatch(r'\s*:?-{2,}:?\s*', c) for c in delimiter)
                or '|' not in lines[index-1]):
            index += 1
            continue
        header = cells(lines[index-1])
        if len(header) != len(delimiter) or len(header) > 80:
            return [], True
        context = '\n'.join(lines[last_end:index-1])[-1800:]
        rows, end = [], index + 1
        while end < len(lines) and '|' in lines[end]:
            row = cells(lines[end])
            if len(row) != len(header) or len(rows) >= 200:
                return [], True
            rows.append(row)
            end += 1
        if not rows:
            return [], True
        found.append((header, rows, context))
        last_end, index = end, end + 1
    # A clipped table without its actual header cannot establish associations.
    suspicious = sum('|' in line and len(cells(line)) >= 2 for line in lines) >= 2
    return found, suspicious


def row_paths(header, rows):
    """Retain explicit indentation ancestry in a categorical label column."""
    label_column = next((i for i in range(len(header)) if any(
        number(row[i]) is None and row[i].strip()
        and len(row[i]) - len(row[i].lstrip()) > 1 for row in rows)), None)
    paths, stack = [], []
    for row in rows:
        if label_column is None:
            paths.append([])
            continue
        raw = row[label_column]
        indentation = len(raw.expandtabs()) - len(raw.expandtabs().lstrip())
        while stack and stack[-1][0] >= indentation:
            stack.pop()
        paths.append([label for _, label in stack])
        if raw.strip() and number(raw) is None:
            stack.append((indentation, raw.strip()))
    return paths


def allowed_labels(point, labels, header, context, period):
    allowed = words(point.population) | words(point.measure) | UNIT_WORDS.get(point.unit, set())
    # A Total row is an aggregate, while Male/Female, age groups, populations,
    # disciplines and metric names must actually be identified by the point.
    ignored = VALUE_HEADERS | {'unit', 'units', 'total'}
    for label in labels:
        if words(label) - allowed - ignored:
            return False
    residual_header = words(header) - words(period) - VALUE_HEADERS
    if residual_header - allowed:
        return False
    association = '\n'.join([context, header, *labels])
    return label_in(point.population, association) and label_in(point.measure, association)


def local_unit_matches(point, cell, header, labels):
    visible = header + ' ' + cell + ' ' + ' '.join(labels)
    known = set()
    if '%' in visible or words(visible) & UNIT_WORDS['percent']:
        known.add('percent')
    if words(visible) & UNIT_WORDS['people']:
        known.add('people')
    if re.search(r'[$\u20ac\u00a3]', visible) or words(visible) & UNIT_WORDS['currency']:
        known.add('currency')
    return not known or known == {point.unit}


def point_cells(point, parsed):
    candidates = []
    for table_index, (header, rows, context) in enumerate(parsed):
        wide_columns = [i for i, h in enumerate(header) if period_in(point.period, h)]
        date_columns = [i for i, h in enumerate(header) if words(h) & PERIOD_HEADERS]
        all_period_columns = {i for i, h in enumerate(header) if re.search(r'\b(?:19|20)\d{2}\b', h)}
        ancestors = row_paths(header, rows)
        for row_index, row in enumerate(rows):
            if wide_columns:
                value_columns = wide_columns
                time_columns = all_period_columns
            else:
                if not any(period_in(point.period, row[i]) for i in date_columns):
                    continue
                time_columns = set(date_columns)
                value_columns = [i for i, h in enumerate(header) if i not in time_columns
                    and number(row[i]) is not None and (words(h) <= VALUE_HEADERS
                        or bool(words(h) & words(point.measure)))]
            for column in value_columns:
                value = number(row[column])
                if value is None:
                    continue
                labels = [*ancestors[row_index], *(cell.strip() for i, cell in enumerate(row)
                    if i != column and i not in time_columns and number(cell) is None and cell.strip())]
                if not allowed_labels(point, labels, header[column], context,
                                      point.period if wide_columns else ''):
                    continue
                if not local_unit_matches(point, row[column], header[column], labels):
                    continue
                candidates.append((table_index, row_index, column, value))
    return candidates


def comparison_cells_match(passage, before, after):
    """Return True/False for table associations, or None for ordinary prose."""
    if not isinstance(passage, str) or len(passage) > 16000:
        return False
    parsed, has_table = tables(passage)
    if not parsed:
        return False if has_table else None
    for point in (before, after):
        matched = point_cells(point, parsed)
        # Select by period/labels FIRST. The desired numeric value must not be
        # used to choose whichever ambiguous row would make the claim true.
        if len(matched) != 1:
            return False
        try:
            expected = Decimal(point.value.replace(',', ''))
        except (InvalidOperation, ValueError, AttributeError):
            return False
        if matched[0][3] != expected:
            return False
    return True
