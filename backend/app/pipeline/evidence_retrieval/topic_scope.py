"""Topic-specific discovery and conservative jurisdiction checks; no truth rules."""

import re
from urllib.parse import unquote, urlsplit

from app.pipeline.shared.jurisdiction import countries_in, scoped_query
from app.pipeline.shared.components import decompose_claim


AUTHORITIES = {
    'policing': ['police.gov.sg', 'mha.gov.sg', 'sso.agc.gov.sg'],
    'healthcare_subsidies': ['moh.gov.sg', 'chas.sg', 'ask.gov.sg', 'mof.gov.sg'],
    'employment': ['mom.gov.sg', 'stats.mom.gov.sg', 'moe.gov.sg', 'singstat.gov.sg'],
    'pensions': ['cpf.gov.sg', 'mom.gov.sg', 'mof.gov.sg'],
    'tax': ['iras.gov.sg', 'mof.gov.sg'],
    'public_policy': ['gov.sg'],
}
GOVERNMENTS = {'gov.sg': 'Singapore', 'gov.au': 'Australia', 'gov.uk': 'United Kingdom',
               'gov.my': 'Malaysia', 'gov.th': 'Thailand', 'gov': 'United States'}
FOREIGN_SCHEMES = {'United States': r'\b(?:Obamacare|Affordable Care Act|HUD|Medicaid)\b',
                   'Australia': r'\b(?:eSafety Commissioner|Centrelink)\b',
                   'United Kingdom': r'\bNHS\b'}


def domains_for(context):
    return AUTHORITIES.get(context.retrieval_topic, []) if context and context.jurisdiction == 'Singapore' else []


def government_country(url):
    host = (urlsplit(str(url)).hostname or '').lower()
    return next((country for suffix, country in GOVERNMENTS.items()
                 if host == suffix or host.endswith('.' + suffix)), None)


def mismatched_jurisdiction(context, url, text):
    if not context or not context.jurisdiction or context.retrieval_topic == 'general':
        return None
    target = context.jurisdiction
    named = countries_in(text)
    if target in named:
        return None  # Comparative pages need passage-level selection, not a URL ban.
    country = government_country(url)
    if country and country != target:
        return f'The page concerns the {country} government; this check concerns {target}.'
    for country, pattern in FOREIGN_SCHEMES.items():
        if country != target and re.search(pattern, text, re.I):
            return f'The passage describes a {country} scheme, not the {target} claim.'
    if named and target not in named and re.search(r'\b(?:government|police|regulator|subsid\w*|households?|graduates?|unemployment)\b', text, re.I):
        return f'The passage names {", ".join(sorted(named))}, not the claim jurisdiction {target}.'
    return None


def page_priority(context, claim, title, url, snippet='', as_of=None):
    domains = domains_for(context)
    if not domains:
        return 0
    host = (urlsplit(str(url)).hostname or '').lower()
    text = title + ' ' + str(url).replace('-', ' ') + ' ' + snippet
    primary = any(host == d or host.endswith('.' + d) for d in domains)
    score = 3 if primary else 1 if context.jurisdiction in countries_in(text) else 0
    patterns = {
        'employment': r'unemployment|graduate employment survey|foreign.worker|salary.requirement|wage',
        'healthcare_subsidies': r'eligib|subsid|means.test|annual.value|private.property',
        'policing': r'clarif|false|online|social.media|speech|offence|legislation',
    }
    if re.search(patterns.get(context.retrieval_topic, r'eligib|policy|rules|announc'), text, re.I):
        score += 2
    if context.retrieval_topic == 'policing' and re.search(r'criticis|criticiz|social.media|\bviews?\b', claim, re.I):
        if re.search(r'criticis|criticiz|opinions?|freedom.of.(?:speech|expression)', text, re.I):
            score += 4
        if re.search(r'\bviews?|viewership|audience\b', text, re.I):
            score += 2
        from .extraction_scope import unrelated_policing_page
        if unrelated_policing_page({'title': title, 'content': snippet}, context, claim):
            score -= 6
    if (context.retrieval_topic == 'healthcare_subsidies' and re.search(r'private propert', claim, re.I)
            and re.search(r'private (?:residential )?propert|private.housing', text, re.I)):
        score += 3
    if context.retrieval_topic == 'employment' and re.search(r'\bgraduates?\b', claim, re.I):
        # Survey PDFs often share a generic title; their filename identifies the
        # institution. Prefer the combined survey for an unqualified population.
        institutions = re.findall(r'\b(?:NUS|NTU|SUTD|SMU|SUSS|SIT)\b', title + ' ' + unquote(str(url)), re.I)
        institutions = [name.upper() for name in institutions]
        if len(set(institutions)) == 1 and not re.search(r'\b' + institutions[0] + r'\b', claim, re.I):
            score -= 2  # A single institution is narrower than all graduates.
    if as_of and not re.search(r'\b(?:19|20)\d{2}\b|\b(?:last|previous|ago)\b', claim, re.I):
        years = [int(y) for y in re.findall(r'\b(20\d{2})\b', title + ' ' + str(url))]
        if years and max(years) < as_of.year - 2:
            score -= 3
    return score


def topic_queries(claim, context):
    if not domains_for(context):
        return []
    topic = context.retrieval_topic
    numbers = ' '.join(re.findall(r'\b\d[\d,]*(?:\.\d+)?\b', claim))
    if topic == 'policing' and re.search(r'social.media|\bposts?\b|criticis|criticiz|\bspeech\b', claim, re.I):
        threshold = ' '.join(re.findall(r'\b\d[\d,]*\s+(?:views?|likes?|shares?)\b', claim, re.I))
        return [f'Singapore police social media government criticism {threshold or numbers} fines official announcement clarification',
                'Singapore criticism government policy opinions POFMA false statements of fact freedom expression MHA']
    if topic == 'healthcare_subsidies':
        housing = 'private property' if re.search(r'\bprivate propert', claim, re.I) else 'households'
        return [f'Singapore {housing} healthcare government subsidies {numbers} changes announcement',
                f'Singapore {housing} healthcare subsidies eligibility income annual value CHAS rules']
    if (topic == 'employment' and decompose_claim(claim) and re.search(r'\bunemployment\b', claim, re.I)
            and re.search(r'\bforeign\w*\b', claim, re.I) and re.search(r'\b(?:salary|wages?|pay)\b', claim, re.I)):
        population = 'graduates autonomous universities joint Graduate Employment Survey' if re.search(r'\bgraduates?\b', claim, re.I) else 'resident labour force survey'
        return [f'Singapore {population} unemployment rate comparison {numbers}',
                f'Singapore foreign workers local workers salary comparison wages work pass salary requirements {numbers}']
    return []


def coverage_gaps(claim, evidence, context):
    if not domains_for(context):
        return []
    applicable = [item for item in evidence
                  if item.provenance and item.provenance.applicability != 'different_scope']
    gaps = []
    if not applicable:
        gaps.append('No applicable passages from the claim jurisdiction were retained.')
    if (context.retrieval_topic == 'policing' and len(applicable) < 2
            and re.search(r'\bwill\b', claim, re.I)):
        gaps.append('Fewer than two applicable official passages cover the alleged new policing rule.')
    if context.retrieval_topic == 'employment' and re.search(r'\bunemployment\b', claim, re.I):
        graduates = bool(re.search(r'\bgraduates?\b', claim, re.I))
        unemployment = [item for item in applicable
                        if re.search(r'\bunemployment\s+(?:rates?|among|of|for)|\bunemployed\b', visible_prose(item.provenance.relevance_quote), re.I)
                        and (not graduates or re.search(r'\bgraduates?\b', item.title + ' ' + item.provenance.relevance_quote, re.I))]
        if not unemployment:
            gaps.append(('Graduate ' if graduates else '') + 'unemployment figures are missing; full-time employment is a different measure.')
        comparisons = [item for item in applicable
                       if re.search(r'\b(?:foreign|migrant|non.resident)\w*\b', item.provenance.relevance_quote, re.I)
                       and re.search(r'\b(?:local|resident|citizen)\w*\b', item.provenance.relevance_quote, re.I)
                       and re.search(r'\b(?:salar\w*|wages?|earnings|pay)\b', item.provenance.relevance_quote, re.I)]
        if re.search(r'\b(?:salary|wages?|pay)\b', claim, re.I) and not comparisons:
            gaps.append('Evidence comparing foreign and local workers pay is missing.')
    return gaps


def visible_prose(text):
    # A link to an unemployment article is not an unemployment figure in the
    # selected passage. Ignore link destinations when checking missing metrics.
    text = re.sub(r'(!?\[[^\]]*\])\([^)]*\)', r'\1', text)
    return re.sub(r'https?://\S+', '', text)


def recovery_query(claim, evidence, context):
    gaps = coverage_gaps(claim, evidence, context)
    if not gaps:
        return None
    if any('unemployment figures' in gap for gap in gaps):
        population = 'Graduate Employment Survey unemployed graduates' if re.search(r'\bgraduates?\b', claim, re.I) else 'resident labour force survey'
        return f'Singapore {population} unemployment rate time series statistics'
    if any('workers pay' in gap for gap in gaps):
        return 'Singapore foreign local employees actual median earnings comparable occupations wage comparison study'
    if context.retrieval_topic == 'policing':
        return 'Singapore MHA POFMA does not cover opinions criticism government policies free express opinions'
    queries = topic_queries(claim, context)
    return (queries[-1] + ' official guidance')[:400] if queries else scoped_query(claim[:320] + ' official current rules', context)


def guard_selection(selection, passage, context, url, claim):
    """Downgrade insufficient scope; never manufacture a decisive passage."""
    mismatch = mismatched_jurisdiction(context, url, selection.quote or passage)
    if mismatch:
        return mismatch
    # Keep semantic scope limitations attached to the passage. Free-form
    # reasons such as "not specifically Singapore graduates" describe a
    # population gap, not a different country. Only the factual jurisdiction
    # check above may reject the page on geography; assessment can still use
    # an otherwise relevant passage for a different material assertion.
    if not context or not context.jurisdiction or selection.relevance == 'irrelevant':
        return None
    if (context.retrieval_topic == 'policing' and selection.relevance == 'direct'
            and re.search(r'\b\d[\d,]*\s+(?:views?|likes?|shares?)\b', claim, re.I)
            and not re.search(r'\b(?:views?|viewership|likes?|shares?|audience|reach|viral)\b', visible_prose(selection.quote), re.I)):
        # A rule about another offence cannot settle an alleged audience-count
        # penalty. It may still be useful baseline context for the later judge.
        selection.relevance = 'context'
        selection.applicability = 'missing_context'
        selection.applicability_reason = 'The quote does not address the alleged audience-count condition. An exception under one law does not establish whether another or a new enforcement rule exists.'
    if context.retrieval_topic != 'general' and selection.applicability == 'established':
        located = context.jurisdiction in countries_in(selection.quote + ' ' + passage)
        if not located and government_country(url) != context.jurisdiction and not any(
                (urlsplit(str(url)).hostname or '').endswith(d) for d in domains_for(context)):
            selection.applicability = 'missing_context'
            selection.applicability_reason = 'The selected passage does not establish the claim jurisdiction.'
    if (context.retrieval_topic == 'employment' and re.search(r'\bunemployment\b', claim, re.I)
            and selection.relevance == 'direct'
            and not re.search(r'\bunemployment\b|\bunemployed\b', visible_prose(selection.quote), re.I)):
        selection.relevance = 'context'
        selection.applicability = 'missing_context'
        selection.applicability_reason = 'The passage concerns employment or earnings, not the alleged unemployment comparison. It may still inform a separate component.'
    return None
