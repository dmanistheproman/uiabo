"""Bounded extraction choices and equivalent-document recovery, never verdicts."""

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

UNAVAILABLE_WARNING = 'Some source pages could not be read, so evidence coverage is incomplete.'
LEAD_WARNING = 'Some websites were used only as leads because their publisher identity was not established by the prototype source policy.'


def html_alternative(url):
    parts = urlsplit(url)
    params = parse_qsl(parts.query, keep_blank_values=True)
    if parts.hostname in {'www.mha.gov.sg', 'mha.gov.sg'} and parts.path.startswith('/mediaroom/media-detail/'):
        return urlunsplit(parts._replace(path=parts.path.replace('/mediaroom/media-detail/', '/media-room/newsroom/', 1)))
    if (parts.hostname == 'sso.agc.gov.sg'
            and any(k.lower() == 'viewtype' and v.lower() == 'pdf' for k, v in params)):
        # Same law, publication and document date; remove only presentation/cache keys.
        return urlunsplit(parts._replace(query=urlencode([
            (k, v) for k, v in params if k.lower() not in {'viewtype', '_'}])))
    return None


def needs_advanced(item, context):
    text = item['url'] + ' ' + item['title'] + ' ' + item.get('content', '')
    return bool(re.search(r'\.pdf(?:\?|$)|viewtype=pdf', item['url'], re.I)
                or context and context.retrieval_topic == 'employment'
                and re.search(r'statistic|survey|infographic|\|[^\n]+\|', text, re.I))


def unrelated_policing_page(item, context, claim):
    if not context or context.retrieval_topic != 'policing':
        return False
    if not re.search(r'criticis|criticiz|social.media|\bviews?\b', claim, re.I):
        return False
    text = item['title'] + ' ' + item.get('content', '')
    return bool(re.search(r'prohibited uniforms|traffic (?:offences?|fines)|fireworks offences', text, re.I)
                and not re.search(r'criticis|criticiz|social.media|opinion|\bviews?\b', text, re.I))


def inference_blockers(retrieval):
    """Legacy/unclassified warnings remain blocking; resolved gaps stay auditable."""
    issues = retrieval.trace.coverage_issues if retrieval.trace else []
    reasons = []
    for warning in retrieval.warnings:
        matches = [i for i in issues if i.warning == warning]
        if not matches:
            reasons.append(warning)
        reasons.extend(i.reason for i in matches if i.blocks_inference and not i.resolved_by)
    reasons.extend(i.reason for i in issues if i.warning not in retrieval.warnings
                   and i.blocks_inference and not i.resolved_by)
    return list(dict.fromkeys(reasons))
