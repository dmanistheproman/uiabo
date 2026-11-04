"""Minimum quoted-period coverage for explicitly dated future policy claims."""

import calendar
from datetime import datetime, time, timezone
import re

from app.pipeline.shared.dates import future_scope_limitation, infer_date_context


def _literal_day(value, text):
    month = calendar.month_name[value.month]
    short_month = calendar.month_abbr[value.month]
    month_pattern = rf'(?:{month}|{short_month}\.?)'
    day = rf'0?{value.day}(?:st|nd|rd|th)?'
    return bool(re.search(
        rf'\b{value.isoformat()}\b|\b{day}\s+{month_pattern}\s+{value.year}\b'
        rf'|\b{month_pattern}\s+{day},?\s+{value.year}\b', text, re.I))


def _covers_period(context, quotes, instant):
    combined = '\n'.join(quotes)
    if context.display_date == str(context.year):
        if future_scope_limitation(context, combined) is None:
            return True
        # A bounded, explicit multi-year schedule can cover a year between its
        # endpoints. An open-ended "from 2027" is deliberately not such a range.
        return any(int(start) <= context.year <= int(end) for start, end in re.findall(
            r'\b((?:19|20|21)\d{2})\s*(?:-|\N{EN DASH}|to|through)\s*((?:19|20|21)\d{2})\b',
            combined, re.I))
    if context.day is None:
        return future_scope_limitation(context, combined) is None
    # Keep a precise future day/range distinct from another day in that month.
    start, end = context.start_date, context.end_date
    if start and end and all(_literal_day(day, combined) for day in {start, end}):
        return True
    for quote in quotes:
        period = infer_date_context(quote, instant)
        if (period and period.basis == 'explicit_date' and period.start_date and period.end_date
                and start and end and period.start_date <= start <= end <= period.end_date):
            return True
    return False


def future_policy_scope_limitation(assertion, finding, *, as_of, claim_context):
    """A nearer-term rule cannot settle a different explicit future period.

    This checks only a necessary date-coverage condition in already bound
    quotations. A matching year/date never establishes the policy's semantic
    scope or a verdict. Undated current claims, historical claims, non-policy
    claims and unresolved findings retain their existing assessment paths.
    """
    if (finding.status == 'unresolved' or as_of is None or claim_context is None
            or claim_context.claim_type != 'policy_change'):
        return None
    text = finding.material_counterfact.claim_span if finding.material_counterfact else assertion.text
    instant = datetime.combine(as_of, time(), timezone.utc)
    context = infer_date_context(text, instant)
    if context is None or context.basis != 'explicit_date' or not context.is_future:
        return None
    quotes = [citation.quote for citation in finding.citations]
    if _covers_period(context, quotes, instant):
        return None
    return (f"The claim specifies {context.display_date}, a future policy period. "
            "The cited quotations do not establish policy for that period. A current rule "
            "or nearer-term adopted schedule cannot by itself establish or refute that later change.")
