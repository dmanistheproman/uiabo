"""Reproducible date intervals based on the Singapore submission clock."""

import calendar
from datetime import date, datetime, timedelta, timezone
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
RELATIVE_DATE = re.compile(r"\b(?:today|tonight|tomorrow|yesterday|(?:this|next|last)\s+(?:weekend|week))\b", re.I)
ISO_DATE = re.compile(r"\b(?P<iso>(?:19|20|21)\d{2}-\d{2}-\d{2})\b")
NAMED_DATE = re.compile(
    rf"\b(?:(?:from|starting|effective|beginning|in|on|by)(?:\s+(?:in|on))?\s+)?"
    rf"(?:(?P<before>{DAY})\s+)?(?P<month>{MONTHS})\b"
    rf"(?:\s+(?P<after>{DAY}))?(?:,?\s+(?P<year>(?:19|20|21)\d{{2}})\b)?", re.I)
NAMED_RANGE = re.compile(
    rf"\b(?P<first>\d{{1,2}})(?:st|nd|rd|th)?\s*(?:-|–|to)\s*"
    rf"(?P<last>\d{{1,2}})(?:st|nd|rd|th)?\s+(?P<month>{MONTHS})"
    rf"(?:,?\s+(?P<year>(?:19|20|21)\d{{2}}))?\b", re.I)
MONTH_FIRST_RANGE = re.compile(
    rf"\b(?P<month>{MONTHS})\s+(?P<first>\d{{1,2}})(?:st|nd|rd|th)?\s*(?:-|–|to)\s*"
    rf"(?P<last>\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(?P<year>(?:19|20|21)\d{{2}}))?\b", re.I)


def submission_time(now=None):
    """Return an aware Singapore instant; legacy naive clocks are treated as UTC."""
    instant = now if now is not None else datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(SINGAPORE)


def _display_date(value):
    return f"{value.day} {calendar.month_name[value.month]} {value.year}"


def _context(fragment, start, end, as_of, basis, *, whole_month=False):
    display = (f"{calendar.month_name[start.month]} {start.year}" if whole_month
               else _display_date(start) if start == end else f"{_display_date(start)} - {_display_date(end)}")
    return DateContext(claim_text=fragment, month=start.month, day=None if whole_month else start.day,
        year=start.year, as_of=as_of, display_date=display, is_future=start > as_of,
        basis=basis, start_date=start, end_date=end)


def _month_number(name):
    return next(i for i, value in enumerate(calendar.month_name) if value.lower() == name.lower())


def infer_date_context(text, now=None):
    """Resolve one clear time expression without changing the original claim.

    Intervals are inclusive. Weeks are Monday to Sunday; this weekend is the
    upcoming Saturday/Sunday, including the current weekend on Saturday/Sunday.
    Ambiguous multiple periods and recurring dates are intentionally unresolved.
    """
    as_of = submission_time(now).date()
    if re.search(r"\b(?:every|each)\s+(?:year|week|weekend|day)\b|\b(?:every|each)\s+(?:" + MONTHS + r")\b", text, re.I):
        return None
    relative = list(RELATIVE_DATE.finditer(text))
    named = [match for match in NAMED_DATE.finditer(text)
             if match['before'] or match['after'] or match['year'] or START_DATE.fullmatch(match.group())]
    iso = list(ISO_DATE.finditer(text))
    if relative:
        if len(relative) != 1 or named or iso:
            return None
        match = relative[0]
        phrase = " ".join(match.group().lower().split())
        if phrase in {"today", "tonight", "tomorrow", "yesterday"}:
            start = end = as_of + timedelta(days={"today": 0, "tonight": 0, "tomorrow": 1, "yesterday": -1}[phrase])
        else:
            which, period = phrase.split()
            monday = as_of - timedelta(days=as_of.weekday())
            offset = {"this": 0, "next": 7, "last": -7}[which]
            start = monday + timedelta(days=offset + (5 if period == "weekend" else 0))
            end = start + timedelta(days=1 if period == "weekend" else 6)
        return _context(match.group(), start, end, as_of, "relative_submission_date")
    if iso:
        if named or len(iso) > 2:
            return None
        try:
            start = date.fromisoformat(iso[0]['iso'])
            end = date.fromisoformat(iso[-1]['iso'])
        except ValueError:
            return None
        if len(iso) == 2 and not re.fullmatch(r"\s*(?:to|through|until|-|–)\s*", text[iso[0].end():iso[1].start()], re.I):
            return None
        if end < start:
            return None
        return _context(text[iso[0].start():iso[-1].end()], start, end, as_of, "explicit_date")
    ranges = [match for pattern in (NAMED_RANGE, MONTH_FIRST_RANGE) for match in pattern.finditer(text)]
    if ranges:
        if len(ranges) != 1 or len(named) != 1:
            return None
        match = ranges[0]
        year = int(match['year']) if match['year'] else as_of.year
        if not match['year'] and re.search(r"\b(?:next|last|previous|following)\s+year\b", text, re.I):
            return None
        try:
            start, end = (date(year, _month_number(match['month']), int(match[name])) for name in ('first', 'last'))
        except ValueError:
            return None
        if end < start:
            return None
        return _context(match.group(), start, end, as_of, "explicit_date" if match['year'] else "assumed_current_year")
    if len(named) == 2:
        first, last = named
        if not re.fullmatch(r"\s*(?:to|through|until|-|–)\s*", text[first.end():last.start()], re.I):
            return None
        first_day, last_day = (match['before'] or match['after'] for match in named)
        if not first_day or not last_day:
            return None
        explicit = bool(first['year'] or last['year'])
        year = int(first['year'] or last['year'] or as_of.year)
        try:
            start = date(int(first['year'] or year), _month_number(first['month']), int(re.match(r"\d+", first_day).group()))
            end = date(int(last['year'] or year), _month_number(last['month']), int(re.match(r"\d+", last_day).group()))
        except ValueError:
            return None
        if end < start:
            return None
        return _context(text[first.start():last.end()], start, end, as_of,
                        "explicit_date" if explicit else "assumed_current_year")
    if len(named) != 1:
        return None
    match = named[0]
    if not (match['before'] or match['after'] or match['year']) and not START_DATE.fullmatch(match.group()):
        return None
    # Monetary amounts such as $2000 or 2000 baht are not explicit years.
    date_text = re.sub(r"[$£€]\s*\d[\d,.]*|\b(?:SGD|USD|THB)\s*\d[\d,.]*"
                       r"|\b\d[\d,.]*\s*(?:baht|dollars?|euros?|pounds?)\b", "", text, flags=re.I)
    if re.search(r"\b(?:next|last|previous|following)\s+year\b", date_text, re.I):
        return None
    if not match['year'] and re.search(r"\b(?:19|20|21)\d{2}\b", date_text, re.I):
        return None
    month = _month_number(match['month'])
    year = int(match['year']) if match['year'] else as_of.year
    day_text = match['before'] or match['after']
    day = int(re.match(r"\d+", day_text).group()) if day_text else None
    if match['before'] and match['after']:
        return None
    if day is not None and not 1 <= day <= calendar.monthrange(year, month)[1]:
        return None
    start = date(year, month, day or 1)
    end = start if day else date(year, month, calendar.monthrange(year, month)[1])
    return _context(match.group(), start, end, as_of,
                    "explicit_date" if match['year'] else "assumed_current_year", whole_month=day is None)


def dated_search_claim(text, context):
    """Discovery-only copy; original text and comparison quotes remain unchanged."""
    if context is None:
        return text
    if context.basis == "explicit_date":
        return text
    if context.basis == "relative_submission_date":
        return text.replace(context.claim_text, context.display_date, 1)
    return text.replace(context.claim_text, f"{context.claim_text} {context.year}", 1)


def assumption_notice(context):
    if context.basis == "relative_submission_date":
        notice = (f"Interpreted date: {context.display_date}, using the submission date "
                  f"{context.as_of.isoformat()} in Asia/Singapore. Relative dates refer to when this check was submitted.")
        if "week" in context.claim_text.lower():
            notice += " Weeks run Monday to Sunday; weekends run Saturday to Sunday."
        return notice
    if context.basis == "explicit_date":
        return f"Stated date: {context.display_date}."
    return (f"Assumed date: {context.display_date}, because the message does not specify a year. "
            "This assessment uses that assumption; correct the year if the message is older or refers to another year.")


def future_scope_limitation(context, passage, *, explicit_denial=False):
    """An existing rule alone cannot refute an alleged future change.

    A matching explicit future period only permits semantic scope assessment;
    it does not establish the rule or independently determine the verdict.
    """
    # The caller must independently validate the denial, quotation and scope.
    # A denial of the alleged change need not repeat its month/year verbatim.
    if context is None or not context.is_future or explicit_denial:
        return None
    month = calendar.month_name[context.month]
    period = (rf"\b(?:{DAY}\s+)?{month}(?:\s+{DAY})?,?\s+{context.year}\b"
              rf"|\b{context.year}-{context.month:02d}(?:-\d{{2}})?\b")
    if re.search(period, passage, re.I):
        return None
    description = "assumed date" if context.basis == "assumed_current_year" else "claim date"
    return (f"The {description}, {context.display_date}, is in the future. "
            "This passage does not explicitly establish policy for that period, so an existing rule cannot disprove the alleged change.")
