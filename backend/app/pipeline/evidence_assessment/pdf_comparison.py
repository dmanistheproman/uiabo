"""Bind numerical comparisons to stored chart points, never a second model's values."""
import re

from .numeric_comparison import (Datum, NumericComparison, _compare_grounded,
                                 claimed_metric, normalise_period, period_key, target_ratio)
from app.pipeline.shared.statistical_dates import uses_latest_statistics


def compare_pdf(text, source, *, population_matches, as_of=None, peers=()):
    reading = source.pdf_reading
    if not reading or target_ratio(text) is None:
        return None
    metric = claimed_metric(text)
    if metric is None and re.search(r'\bunemployment\b', text, re.I):
        metric = 'unemployed_count'  # Context only: missing_measure blocks a vote.
    candidates = [s for s in reading.document.series if s.metric_type == metric and len(s.points) >= 2]
    period_text = normalise_period(text)
    as_of = as_of or source.retrieved_at.date()
    recent = uses_latest_statistics(text)
    choices = []
    for series in candidates:
        if recent:
            valid = [p for p in series.points if period_key(p.date_label)]
            keys = [period_key(p.date_label) for p in valid]
            if len(set(keys)) != len(keys):
                continue  # Multiple cohorts/values at the same date are ambiguous.
            matched = sorted(valid, key=lambda p: period_key(p.date_label))[-2:]
        else:
            matched = [p for p in series.points if normalise_period(p.date_label) in period_text]
        if len(matched) == 2:
            choices.append((series, matched))
    if recent and len(choices) > 1:
        groups = {(s.population_label.casefold(), s.metric_label.casefold(),
                   tuple(p.unit for p in pts)) for s, pts in choices}
        if len(groups) == 1:
            newest = max(period_key(pts[-1].date_label) for _, pts in choices)
            choices = [(s, pts) for s, pts in choices if period_key(pts[-1].date_label) == newest]
    if len(choices) != 1:
        # Explicit non-matching dates can still receive context, never a vote.
        if not recent and len(candidates) == 1 and len(candidates[0].points) == 2 and not choices:
            series, points = candidates[0], candidates[0].points
        else:
            return None, ['ambiguous_pdf_comparison'], 'The PDF does not establish one unambiguous comparison for this claim.'
    else:
        series, points = choices[0]
    # Use printed dates for scope/arithmetic; normalised model dates never supply
    # missing labels. Cohort/population interpretation still requires assessment.
    points = sorted(points, key=lambda p: period_key(p.date_label) or (0, 0))
    def datum(p):
        return Datum(value=p.value, period=p.date_label, population=series.population_label,
                     measure=series.metric_label, metric=series.metric_type, unit=p.unit)
    context = series.population_label + ' ' + source.passage
    data = NumericComparison(quote=context[:12000], before=datum(points[0]), after=datum(points[1]),
                             population_matches_claim=population_matches)
    # Only the same measurement/population can supersede this series. A newer
    # rate, publication date or different population cannot replace a count.
    normalise = lambda label: ' '.join(re.findall(r'\w+', label.casefold()))
    peer_dates = [period_key(p.date_label) for peer in peers if peer.pdf_reading
                  for other in peer.pdf_reading.document.series
                  if other.metric_type == series.metric_type
                  and normalise(other.population_label) == normalise(series.population_label)
                  for p in other.points if p.unit == points[-1].unit and period_key(p.date_label)]
    peer_dates = [p for p in peer_dates if p <= (as_of.year, as_of.month)]
    known = max(peer_dates) if peer_dates else None
    stance, gaps, reason = _compare_grounded(text, data, as_of=as_of, latest_known=known,
        available_periods=[p.date_label for p in series.points])
    if reading.document.limitations:
        # Until limitations can be reliably attached to individual series, keep
        # the whole reading contextual rather than ignoring an extraction caveat.
        stance = None
        gaps = list(dict.fromkeys([*gaps, 'pdf_extraction_limitations']))
    return stance, gaps, (f'Reading of the PDF chart on page {series.page}: ' + reason +
        ' The figures were read with Gemini and checked against PDF text; the chart associations are model-interpreted.')


def guard_pool_comparison(text, source, item, *, as_of=None, peers=()):
    if not source.pdf_reading or target_ratio(text) is None:
        return
    # Whole-claim applicability must already be established by retrieval and
    # assessment. This guard can remove a vote but cannot manufacture confidence.
    established = bool(source.provenance and source.provenance.applicability == 'established')
    result = compare_pdf(text, source, population_matches=established, as_of=as_of, peers=peers)
    if result is None:
        result = (None, ['missing_comparison'], 'The PDF supplies no verified comparison for this claimed change.')
    stance, gaps, reason = result
    item.assessment_reason = reason
    if gaps or not stance or item.stance == 'neutral':
        item.stance = 'neutral'
        item.quality_score = 0
    else:
        item.stance = stance
