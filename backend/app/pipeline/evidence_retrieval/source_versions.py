"""Explicit document-version dates, separate from ordinary publication dates."""

import calendar
from datetime import date
import re
from urllib.parse import parse_qs, urlsplit


def _date(value):
    compact = value.replace('-', '')
    if not re.fullmatch(r'(?:19|20|21)\d{6}', compact):
        return None
    try:
        return date(int(compact[:4]), int(compact[4:6]), int(compact[6:]))
    except ValueError:
        return None


def source_version_context(url: str | None, text: str = '') -> dict | None:
    """Identify selected snapshots, never infer expiry from a page's age.

    The SSO DocDate selects a legislative edition, whereas Published in the
    archive route can name a different date. Neither is evidence that the
    snapshot remains the current law. An unversioned Act URL (including its
    enactment year) and an ordinary publication date are deliberately ignored.
    """
    parsed = urlsplit(url or '')
    query = {key.casefold(): values for key, values in parse_qs(parsed.query).items()}
    version, basis = None, None
    if parsed.hostname == 'sso.agc.gov.sg':
        doc_dates = query.get('docdate', [])
        if len(doc_dates) == 1:
            version = _date(doc_dates[0])
            if version:
                basis = 'selected_edition_docdate'
        if version is None:
            match = re.search(r'/Act-Rev/[^/]+/Published/(\d{8})(?:/|$)', parsed.path, re.I)
            if match:
                version = _date(match[1])
                basis = 'dated_legislation_archive'
    # Other publishers can expose an explicit dated historical/version route.
    # A generic /news/2000/... or /archive/2000/... is not a version selector.
    if version is None:
        match = re.search(r'/(?:historical|archived|versions?|point-in-time)/(\d{4}-\d{2}-\d{2}|\d{8})(?:/|$)',
                          parsed.path, re.I)
        if match:
            version = _date(match[1])
            basis = 'dated_version_route'
    if version is None:
        # Require a page-level version label, not a date mentioned in a quoted
        # provision, a historical discussion, or a revised-edition publication.
        match = re.search(r'^\s*(?:#{1,6}\s*)?(?:Historical|Archived|Superseded|Point-in-time)\s+'
                          r'version\s*(?:as\s+(?:at|of)|:)?\s*(\d{4}-\d{2}-\d{2}|\d{8})\b',
                          text[:100000], re.I | re.M)
        if match:
            version = _date(match[1])
            basis = 'explicit_historical_version_label'
    if version is None:
        return None
    return {'kind': 'dated_version', 'version_date': version.isoformat(), 'basis': basis}


def current_version_limitation(version, *, as_of, date_context=None):
    """Retain past snapshots as context without asserting they are superseded.

    Historical claims remain available to the semantic period/scope check.
    Current corroboration must come from another source; this individual
    snapshot cannot independently prove that its rule still applies today.
    """
    if version is None or date.fromisoformat(version['version_date']) >= as_of:
        return None
    if date_context is not None:
        end = date_context.end_date or date(date_context.year, date_context.month,
                                          date_context.day or calendar.monthrange(date_context.year, date_context.month)[1])
        if end < as_of:
            return None
    return (f"This source is an explicitly selected version dated {version['version_date']}. "
            "It can provide historical context, but does not by itself establish the current "
            "rule or an alleged change; current applicability needs independent corroboration.")


def exclude_archived_current_policy_source(url: str | None, text: str = '', *,
                                          as_of: date | None, date_context=None) -> bool:
    """Exclude explicit old archives from a current-policy proof, not retrieval.

    Call only for a current-policy assertion, using that assertion's date
    context. Historical assertions retain the document for semantic checking.
    A snapshot may contain unchanged facts, but cannot independently establish
    today's rule. This flag does NOT claim that every provision is obsolete.

    This is narrower than current_version_limitation: an old DocDate alone or
    generic /versions/ route does not prove the selected edition is archival.
    Ordinary publication dates and enactment years never trigger exclusion.
    """
    if as_of is None:
        return False
    parsed = urlsplit(str(url) if url else '')
    archive_route = (
        parsed.hostname == 'sso.agc.gov.sg'
        and re.search(r'^/Act-Rev/[^/]+(?:/|$)', parsed.path, re.I)
    ) or re.search(r'/(?:historical|archived)/(\d{4}-\d{2}-\d{2}|\d{8})(?:/|$)',
                   parsed.path, re.I)
    version = source_version_context(str(url) if url else None, text) if archive_route else None
    if version is None:
        # A page-level historical label is stronger than a bare edition date.
        # Bound the header search so a later discussion of old versions cannot
        # suppress a current page. "Point-in-time" alone is not archival status.
        label = re.search(r'^\s*(?:#{1,6}\s*)?(?:Historical|Archived|Superseded)\s+'
                          r'version\s*(?:as\s+(?:at|of)|:)?\s*(\d{4}-\d{2}-\d{2}|\d{8})\b',
                          text[:3000], re.I | re.M)
        historical_date = _date(label[1]) if label else None
        if historical_date:
            version = {'version_date': historical_date.isoformat()}
    return current_version_limitation(version, as_of=as_of, date_context=date_context) is not None
