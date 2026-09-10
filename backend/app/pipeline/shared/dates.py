"""Explicit, reproducible year assumptions for named dates in claims."""

import calendar
from datetime import datetime, timedelta, timezone
import re

from .models import DateContext

SINGAPORE = timezone(timedelta(hours=8))
MONTHS = "|".join(calendar.month_name[1:])
DAY = r"\d{1,2}(?:st|nd|rd|th)?\b"
START_DATE = re.compile(
    r"\b(?:from|starting|effective|beginning|in|on|by)(?:\s+(?:in|on))?\s+"
    rf"(?:(?P<before>{DAY})\s+)?(?P<month>{MONTHS})\b"
    rf"(?:\s+(?P<after>{DAY}))?(?:,?\s+(?P<year>(?:19|20|21)\d{{2}})\b)?",
    re.I,
)


def infer_date_context(text, now=None):
    """Do not reinterpret explicit years, recurring dates or relative years.

    More than one named start date or another explicit year needs richer date
    interpretation; leave those ambiguous claims to the existing scope checks.
    """
    matches = list(START_DATE.finditer(text))
    if len(matches) != 1 or matches[0]['year']:
        return None
    # Monetary amounts such as $2000 or 2000 baht are not explicit years.
    date_text = re.sub(r"[$£€]\s*\d[\d,.]*|\b(?:SGD|USD|THB)\s*\d[\d,.]*"
                       r"|\b\d[\d,.]*\s*(?:baht|dollars?|euros?|pounds?)\b", "", text, flags=re.I)
    if re.search(r"\b(?:19|20|21)\d{2}\b|\b(?:next|last|previous|following)\s+year\b", date_text, re.I):
        return None
    match = matches[0]
    # 'every year from October' is recurring, not a dated announcement.
    if re.search(r"\b(?:every|each)\s+year\b", text, re.I):
        return None
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    as_of = now.astimezone(SINGAPORE).date()
    month = next(i for i, name in enumerate(calendar.month_name) if name.lower() == match['month'].lower())
    day_text = match['before'] or match['after']
    day = int(re.match(r"\d+", day_text).group()) if day_text else None
    if day and day > calendar.monthrange(as_of.year, month)[1]:
        return None
    future = month > as_of.month or (month == as_of.month and day is not None and day > as_of.day)
    display = f"{day} " if day else ""
    display += f"{calendar.month_name[month]} {as_of.year}"
    return DateContext(claim_text=match.group(), month=month, day=day, year=as_of.year,
                       as_of=as_of, display_date=display, is_future=future)


def dated_search_claim(text, context):
    """Discovery-only copy; original text and comparison quotes remain unchanged."""
    if context is None:
        return text
    return text.replace(context.claim_text, f"{context.claim_text} {context.year}", 1)


def assumption_notice(context):
    return (f"Assumed date: {context.display_date}, because the message does not specify a year. "
            "This assessment uses that assumption; correct the year if the message is older or refers to another year.")


def future_scope_limitation(context, passage):
    """An existing rule alone cannot refute an alleged future change.

    A matching explicit future period only permits semantic scope assessment;
    it does not establish the rule or independently determine the verdict.
    """
    if context is None or not context.is_future:
        return None
    month = calendar.month_name[context.month]
    period = (rf"\b(?:{DAY}\s+)?{month}(?:\s+{DAY})?,?\s+{context.year}\b"
              rf"|\b{context.year}-{context.month:02d}(?:-\d{{2}})?\b")
    if re.search(period, passage, re.I):
        return None
    return (f"The assumed date, {context.display_date}, is in the future. "
            "This passage does not explicitly establish policy for that period, so an existing rule cannot disprove the alleged change.")
