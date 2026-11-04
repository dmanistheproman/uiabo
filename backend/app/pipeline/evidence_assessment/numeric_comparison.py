"""Quoted statistical comparisons. Models extract; Decimal performs arithmetic.

No source figures, dates or expected verdicts are built into this module.
Undated claims use a disclosed latest-comparable-period default when a submission
date and sufficiently recent observations are available.
"""

from decimal import Decimal, InvalidOperation
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from app.pipeline.shared.statistical_dates import uses_latest_statistics

Metric = Literal['unemployment_rate', 'unemployed_count', 'employment_rate',
                 'actual_salary', 'salary_minimum', 'other']


class Datum(BaseModel):
    model_config = ConfigDict(extra='forbid')
    value: str = Field(min_length=1, max_length=30)
    period: str = Field(min_length=1, max_length=100)
    population: str = Field(min_length=1, max_length=200)
    measure: str = Field(min_length=1, max_length=200)
    metric: Metric
    unit: Literal['percent', 'people', 'currency', 'other']


class NumericComparison(BaseModel):
    model_config = ConfigDict(extra='forbid')
    quote: str = Field(min_length=10, max_length=12000)
    before: Datum
    after: Datum
    population_matches_claim: bool
    scope_gaps: list[Literal['missing_period', 'different_period', 'different_population',
                            'missing_measure', 'different_measure', 'incomparable_groups']] = Field(default_factory=list)


NUMERIC_GUIDANCE = """
For a component asserting doubled, tripled, halved or a percentage change, include
comparison (null if no comparable figures) with this shape:
{"before":{"value":"literal numeric token WITHOUT percent sign", "period":"literal period label",
 "population":"literal population label", "measure":"literal metric label",
 "metric":"unemployment_rate|unemployed_count|employment_rate|actual_salary|salary_minimum|other",
 "unit":"percent|people|currency|other"}, "after":{same fields},
 "population_matches_claim":true, "scope_gaps":[]}
The backend binds the supplied source passage as the quotation. Do not write a quote.
Copy every label from that passage except the metric/unit classification. No invented
years or reconstructed table rows. Before and after must be ordered chronologically.
Choose the comparison matching the CLAIM period, not one that makes it false.
If the claim has no date or historical/relative interval, interpret it as a recent
change: select the newest two comparable OBSERVATION periods for the SAME population,
measurement and units. Do not select an older convenient baseline. The backend
checks this default and discloses the dates. Missing dates alone are not a scope
gap for that default. An explicit period always takes priority. If no comparable
pair is available, leave comparison null. Other scope_gaps: different_period,
different_population, missing_measure, different_measure, incomparable_groups.
Fresh graduates are not all graduates. Rates, counts, full-time employment rates
and employment rates are not interchangeable. Do not derive unemployment by
subtracting employment from 100 without the source's correct denominator.
Actual foreign/local salaries require comparable workers, roles and periods;
work-pass eligibility minima do not establish actual earnings or a half-pay ratio.
For numerical components with no usable figures, leave comparison null and explain
what is missing. Never calculate or guess the ratio yourself; the backend does it.
For other components omit comparison or use null.
"""


def target_ratio(text):
    if re.search(r'\b(?:not|never|will|could|might|forecast\w*|expect\w*|almost|nearly|about|approximately)\b|\b(?:at least|at most|more than|less than)\b|\bmay\s+(?:double|triple|halve|increase|decrease)', text, re.I):
        return None  # Qualifiers/forecasts require their own semantics, not equality.
    if re.search(r'\bdoubl(?:ed|ing|e)\b', text, re.I):
        return Decimal(2)
    if re.search(r'\btripl(?:ed|ing|e)\b', text, re.I):
        return Decimal(3)
    if re.search(r'\bhalved\b', text, re.I):
        return Decimal('.5')
    match = re.search(r'\b(increas(?:ed|e)|decreas(?:ed|e)|rose|fell|grew)\s+(?:by\s+)?(\d+(?:\.\d+)?)\s*(?:%|per\s*cent|percent)(?!\w)', text, re.I)
    if match:
        delta = Decimal(match[2]) / 100
        return 1 - delta if match[1].lower().startswith(('decreas', 'fell')) else 1 + delta
    return None


def claimed_metric(text):
    if re.search(r'\bunemployment rate\b', text, re.I):
        return 'unemployment_rate'
    if re.search(r'\b(?:number|count)\b.*\bunemployed\b', text, re.I):
        return 'unemployed_count'
    if re.search(r'\bemployment rate\b', text, re.I):
        return 'employment_rate'
    return None


def claim_limitations(text):
    if target_ratio(text) is None:
        return []
    limits = []
    years = re.findall(r'\b20\d{2}\b', text)
    months = re.findall(r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\b', normalise_period(text), re.I)
    if not uses_latest_statistics(text) and len(years) < 2 and not (years and len(months) >= 2):
        limits.append('Give the two dates or periods being compared so we can check the claimed change.')
    if re.search(r'\bunemployment\b', text, re.I) and claimed_metric(text) is None:
        limits.append('Specify whether unemployment means the percentage unemployed or the number of unemployed people.')
    return limits


def normalise_period(text):
    text = re.sub(r"[’'](\d{2})\b", lambda m: ' 20' + m[1], text)
    for short, full in [('jan', 'january'), ('feb', 'february'), ('mar', 'march'),
                        ('apr', 'april'), ('jun', 'june'), ('jul', 'july'), ('aug', 'august'),
                        ('sep', 'september'), ('sept', 'september'), ('oct', 'october'),
                        ('nov', 'november'), ('dec', 'december')]:
        text = re.sub(r'\b' + short + r'\b\.?', full, text, flags=re.I)
    return re.sub(r'\s+', ' ', text).strip().lower()


def period_key(text):
    months = 'january february march april may june july august september october november december'.split()
    text = normalise_period(text)
    match = re.fullmatch(r'(?:(\w+)\s+)?(20\d{2})', text)
    if not match or match[1] and match[1] not in months:
        return None
    return int(match[2]), months.index(match[1]) + 1 if match[1] else 0


def decimal_value(token):
    if not re.fullmatch(r'(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?', token):
        raise ValueError('Unsupported numeric token')
    try:
        return Decimal(token.replace(',', ''))
    except InvalidOperation as exc:
        raise ValueError('Invalid value') from exc


def _literal_value(value, quote):
    return bool(re.search(r'(?<![\d.,])' + re.escape(value) + r'(?!\d|[.,]\d)', quote))


def _literal_label(label, passage):
    # Typography and line wrapping are immaterial for a metadata label. The
    # evidence quotation itself stays the exact source text.
    normalise = lambda value: re.sub(r'\s+', ' ', value.replace('’', "'")).strip().casefold()
    return normalise(label) in normalise(passage)


def population_phrase(label, passage):
    """Resolve a reordered noun label to a short literal source phrase.

    E.g. '2025 cohort graduates' -> 'graduates from the 2025 cohort'. Every
    content word must occur in one short clause. No new country, 'all', year,
    negation or population qualifier can be inserted or discarded.
    """
    if _literal_label(label, passage):
        return label
    stop = {'the', 'of', 'in', 'for', 'among', 'a', 'an', 'from'}
    required = set(re.findall(r'\w+', label.casefold())) - stop
    if not required or required & {'not', 'no', 'except', 'excluding'}:
        return None
    words = list(re.finditer(r'\w+', passage))
    choices = []
    for i, word in enumerate(words):
        if word[0].casefold() not in required:
            continue
        for end in words[i:i + 20]:
            candidate = passage[word.start():end.end()]
            if len(candidate) > 120 or re.search(r'[.!?;\n]', candidate):
                break
            tokens = set(re.findall(r'\w+', candidate.casefold()))
            if required <= tokens and not tokens & {'not', 'no', 'except', 'excluding'}:
                choices.append(candidate)
                break
    return min(choices, key=len) if choices else None


def compare(text, passage, data, *, as_of=None, latest_known=None):
    """Return a grounded summary and an optional vote; any scope gap blocks it."""
    if data.quote not in passage:
        raise ValueError('Comparison quotation is not in the source passage')
    data = data.model_copy(deep=True)
    for point in (data.before, data.after):
        population = population_phrase(point.population, data.quote)
        if population is None:
            raise ValueError('Comparison population is not grounded in the quotation')
        point.population = population
        if not _literal_label(point.measure, data.quote):
            # A model may name the measure as "number of unemployed graduates"
            # when a chart labels the row "Unemployed". Bind the actual label,
            # keeping count and rate vocabularies separate.
            pattern = {'unemployed_count': r'\bUnemployed\b',
                       'unemployment_rate': r'\bunemployment\s+rate\b',
                       'employment_rate': r'(?<!un)\bemployment\s+rate\b'}.get(point.metric)
            match = re.search(pattern, data.quote, re.I) if pattern else None
            if match:
                point.measure = match[0]
        if (not _literal_value(point.value, data.quote)
                or any(not _literal_label(label, data.quote) for label in (point.period, point.population, point.measure))):
            raise ValueError('Comparison value or label is not in the quotation')
    from .tabular_grounding import comparison_cells_match
    if comparison_cells_match(data.quote, data.before, data.after) is False:
        raise ValueError('Comparison values cannot be associated with their table labels')
    return _compare_grounded(text, data, as_of=as_of, latest_known=latest_known)


def latest_period_check(text, data, as_of, latest_known=None, available_periods=None):
    """Choose by chronology/cadence, never by values or the desired verdict."""
    if not uses_latest_statistics(text) or as_of is None:
        return False, [], ''
    keys = [period_key(p.period) for p in (data.before, data.after)]
    notice = (f'No dates were given, so we used the latest comparable figures found: '
              f'{data.before.period} to {data.after.period}. ')
    if any(k is None for k in keys) or keys[0] >= keys[1]:
        return True, ['different_period'], 'The source dates could not establish a latest-period comparison. '
    before, after = keys
    if bool(before[1]) != bool(after[1]):
        return True, ['incomparable_periods'], 'The source uses different reporting periods, so no recent comparison was assumed. '
    step = (after[0] - before[0]) * 12 + after[1] - before[1]
    # Annual, quarterly-spaced monthly labels, or monthly observations. Irregular
    # multi-year comparisons need explicit dates rather than a guessed baseline.
    if step not in ({1, 3, 12} if after[1] else {12}):
        return True, ['incomparable_periods'], 'The observations do not provide an adjacent supported reporting interval for the recent-change default. '
    now = (as_of.year, as_of.month)
    age = (now[0] - after[0]) * 12 + (now[1] - (after[1] or 12))
    if age < 0:
        return True, ['future_statistics'], 'The pair includes a future period, so it was not used as current statistics. '
    # One reporting interval plus a publication-lag allowance. This does not
    # claim the source is globally latest; it blocks treating old data as recent.
    if age > {1: 3, 3: 9, 12: 24}[step]:
        return True, ['outdated_statistics'], (f'The newest comparable figures found cover '
            f'{data.before.period} to {data.after.period}, but are too old for the recent-change default. ')
    # A selected pair cannot omit a newer comparable printed period. Only use
    # matching precision; publication years do not replace monthly observations.
    pattern = (r'\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)[ .]*(?:[\u2019\']\d{2}|20\d{2})\b'
               if after[1] else r'\b20\d{2}\b')
    printed = ([period_key(p) for p in available_periods] if available_periods is not None
               else [period_key(m[0]) for m in re.finditer(pattern, data.quote, re.I)])
    candidates = [k for k in [*printed, latest_known] if k and bool(k[1]) == bool(after[1]) and k <= now]
    if candidates and max(candidates) > after:
        return True, ['newer_statistics_available'], 'A newer comparable period is available; this older pair was not used for the undated claim. '
    if any(before < k < after for k in candidates):
        return True, ['non_latest_baseline'], 'An intervening observation is available; the older baseline was not used for the undated claim. '
    return True, [], notice


def _compare_grounded(text, data, *, as_of=None, latest_known=None, available_periods=None):
    """Arithmetic shared by literal quotations and corroborated PDF readings.

    Callers must bind data to their respective source representation first.
    """
    first, last = data.before, data.after
    gaps = list(data.scope_gaps)
    assumed, date_gaps, notice = latest_period_check(text, data, as_of, latest_known, available_periods)
    if assumed:
        # Recompute date suitability against the server-owned default. A model's
        # objection to the absent literal dates must not reinstate the old rule.
        gaps = [g for g in gaps if g not in {'missing_period', 'different_period'}] + date_gaps
    # A named general metric is not an unidentified measurement. Both points
    # must use the same literal label, and that label must occur in the claim.
    generic_label = re.sub(r'\s+', ' ', first.measure).strip().casefold()
    named_generic = (first.metric == 'other' and first.unit != 'other'
        and generic_label == re.sub(r'\s+', ' ', last.measure).strip().casefold()
        and generic_label not in {'rate', 'count', 'number', 'amount', 'total', 'percentage', 'value'}
        and _literal_label(first.measure, text))
    if first.metric != last.metric or first.unit != last.unit or (first.metric == 'other' and not named_generic):
        return None, ['different_measure'], 'The figures use different or unidentified measurements; no change was calculated.'
    if (((first.metric.endswith('_rate') or (named_generic and re.search(r'\b(?:rate|percentage|proportion)\b', generic_label))) and first.unit != 'percent')
            or (first.metric == 'unemployed_count' and first.unit != 'people')
            or (first.unit == 'people' and any(re.search(re.escape(p.value) + r'\s*(?:%|per cent|percent)', data.quote, re.I)
                                             for p in (first, last)))):
        return None, ['different_measure'], 'A percentage and a count cannot be substituted for one another.'
    if first.population != last.population or not data.population_matches_claim:
        gaps.append('different_population')
    if (re.search(r'\bgraduates?\b', text, re.I)
            and re.search(r'\b(?:fresh|recent|newly)[^.!?\n]{0,45}\bgraduates?\b', data.quote, re.I)
            and not re.search(r'\bfresh|recent|newly\b', text, re.I)):
        gaps.append('different_population')
    metric = claimed_metric(text)
    if re.search(r'\bunemployment\b|\bunemployed\b', text, re.I):
        if metric is None:
            gaps.append('missing_measure')
        elif metric != first.metric:
            gaps.append('different_measure')
    if first.metric == 'salary_minimum':
        gaps.append('different_measure')
    period_text = normalise_period(text)
    periods = [normalise_period(p.period) for p in (first, last)]
    chronology = [period_key(p) for p in periods]
    if any(p is None for p in chronology) or chronology[0] >= chronology[1]:
        gaps.append('different_period')
    if not assumed and not all(p in period_text for p in periods):
        gaps.append('different_period' if len(re.findall(r'\b20\d{2}\b', text)) >= 2 else 'missing_period')
    a, b = decimal_value(first.value), decimal_value(last.value)
    if a <= 0:
        return None, ['zero_baseline'], 'The baseline is zero, so a percentage change or doubling ratio cannot be calculated.'
    ratio = b / a
    change = (ratio - 1) * 100
    # Respect the last published decimal place. Rounded data supports consistency
    # with a ratio, not an assertion of infinitely precise equality.
    precision_a = Decimal(0) if first.unit == 'people' else Decimal(1).scaleb(a.as_tuple().exponent) / 2
    precision_b = Decimal(0) if first.unit == 'people' else Decimal(1).scaleb(b.as_tuple().exponent) / 2
    low = max(Decimal(0), b - precision_b) / (a + precision_a)
    high = (b + precision_b) / (a - precision_a) if a > precision_a else Decimal('Infinity')
    summary = (f'The source reports {first.value} ({first.period}) and {last.value} ({last.period}) '
               f'for {first.population}, measured as {first.measure}. '
               f'That is {ratio:.2f} times the earlier figure, a {abs(change):.1f}% '
               f'{"increase" if change >= 0 else "decrease"}.')
    gaps = list(dict.fromkeys(gaps))
    target = target_ratio(text)
    claimed_precision = re.search(r'\b(\d+(?:\.\d+)?)\s*(?:%|per\s*cent|percent)(?!\w)', text, re.I)
    tolerance = (Decimal(1).scaleb(Decimal(claimed_precision[1]).as_tuple().exponent) / 200
                 if claimed_precision and target is not None and not re.search(r'\b(?:doubl\w*|tripl\w*|halved)\b', text, re.I)
                 else Decimal(0))
    stance = None if gaps or target is None else 'supporting' if low <= target + tolerance and target - tolerance <= high else 'contradicting'
    if stance == 'supporting':
        summary += ' The reported precision is consistent with the claimed change.'
    elif stance == 'contradicting':
        summary += ' This differs from the claimed change for that comparison.'
    reasons = {
        'missing_period': 'The message does not identify both comparison periods; these dates are context, not an assumed baseline.',
        'different_period': 'The source periods do not match the periods stated in the message.',
        'different_population': 'The source population does not establish the full group described in the message.',
        'missing_measure': 'The message does not say whether unemployment means the rate or the number of people.',
        'different_measure': 'The source measurement does not establish the measurement alleged in the message.',
        'incomparable_groups': 'The groups being compared are not established as comparable.',
        'incomparable_periods': 'The observations do not provide adjacent periods of the same reporting frequency.',
        'future_statistics': 'A future observation cannot be treated as a current published statistic.',
        'outdated_statistics': 'More recent figures are needed to apply the recent-change assumption.',
        'newer_statistics_available': 'Use the newer comparable observations found.',
        'non_latest_baseline': 'Use the immediately preceding comparable observation.',
    }
    return stance, gaps, notice + ' '.join([summary, *(reasons.get(g, g) for g in gaps)])
