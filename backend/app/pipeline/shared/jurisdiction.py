"""Discovery scope, not a verdict. Defaults are explicit and never rewrite claims."""

import re
from babel import Locale


# Aliases are discovery hints. Unrecognised named places remain unresolved rather
# than being silently mapped to Singapore. Keep multi-country claims unresolved.
COUNTRIES = {
    'Singapore': r'Singapore(?:ans?)?|SG',
    'Malaysia': r'Malaysia(?:ns?)?|Kuala Lumpur|Johor(?: Bahru)?|Penang',
    'Australia': r'Australia(?:ns?)?|Sydney|Melbourne|Canberra',
    'United States': r'United States|USA|U\.S\.(?:A\.)?|American(?:s)?|New York|California',
    'United Kingdom': r'United Kingdom|UK|Britain|British|England|London',
    'Thailand': r'Thailand|Thai|Bangkok|Phuket',
    'Indonesia': r'Indonesia(?:ns?)?|Jakarta|Bali',
    'Philippines': r'Philippines|Filipino(?:s)?|Manila',
    'India': r'India(?:ns?)?|Mumbai|Delhi',
    'China': r'China|Chinese|Beijing|Shanghai',
    'Hong Kong': r'Hong Kong', 'Taiwan': r'Taiwan(?:ese)?',
    'Japan': r'Japan(?:ese)?|Tokyo', 'South Korea': r'South Korea(?:n)?|Seoul',
    'New Zealand': r'New Zealand|Auckland', 'Canada': r'Canada|Canadian(?:s)?|Toronto',
    'France': r'France|French|Paris', 'Germany': r'Germany|German(?:s)?|Berlin',
    'Vietnam': r'Vietnam(?:ese)?|Hanoi', 'Brunei': r'Brunei',
    'Cambodia': r'Cambodia(?:n)?', 'Myanmar': r'Myanmar|Burma',
    'Brazil': r'Brazil(?:ian)?', 'Russia': r'Russia(?:n)?',
}
# CLDR supplies country/territory names beyond the common aliases above. This
# prevents an explicitly named less-common country from taking the SG default.
for _code, _name in Locale.parse('en').territories.items():
    if len(_code) == 2 and _code.isalpha() and _code not in {'EU', 'EZ', 'UN', 'XA', 'XB', 'ZZ'}:
        COUNTRIES.setdefault(_name, re.escape(_name))
_COUNTRY_PATTERNS = [(country, re.compile(r'(?<!\w)(?:' + pattern + r')(?!\w)', re.I))
                     for country, pattern in COUNTRIES.items()]
TOPICS = (
    ('policing', r'\b(?:police|fines?|penalt(?:y|ies)|arrest\w*)\b.*\b(?:social.media|posts?|criticis\w*|criticiz\w*|government|speech)\b'),
    ('healthcare_subsidies', r'\bCHAS\b|\b(?:subsid\w*|benefits?)\b.*\b(?:health\w*|medical)\b|\b(?:health\w*|medical)\b.*\b(?:subsid\w*|benefits?)\b'),
    # A verb such as "students graduate later" describes education, not an
    # employment statistic. Graduate-related employment needs an employment
    # predicate; the noun alone must not route admissions rules to MOM.
    ('employment', r'\b(?:unemployment|underemployment|hiring|foreign.workers?|work.passes?|employment.rates?|graduate.employment)\b|\bgraduates?\b.{0,65}\b(?:jobs?|workforce|salaries|salary|earnings|employed|unemployed)\b'),
    ('pensions', r'\b(?:CPF|MediSave|MediShield|pensions?|retirement.age)\b'),
    ('tax', r'\b(?:tax(?:es|ation)?|GST|income.tax)\b'),
    ('public_policy', r'\b(?:government|public.policy|policies|subsidies|legislation)\b'),
)
DOMESTIC = re.compile(r'\b(?:government|police|households?|residents?|citizens?|subsid\w*|employment|unemployment|graduates?|hiring|tax(?:es)?|CPF|MediSave|MediShield|CHAS|GST|retirement)\b', re.I)
SG_AUTHORITY = re.compile(r'\b(?:Central Provident Fund|CPF|MediSave|MediShield|CHAS|HDB|Singpass|SkillsFuture)\b', re.I)
FOREIGN_AUTHORITY = re.compile(r'\b(?:Obamacare|ACA|HUD|eSafety|IRS|NHS|EPF|KWSP|Centrelink)\b', re.I)
SG_ASSUMPTION = 'Assuming this domestic policy or employment claim refers to Singapore because no country was specified. A named country takes priority.'
NON_PLACES = re.compile(r'^(?:private|public|rental|residential|commercial)\s+(?:property|properties|housing|homes?|estates?)\b|^(?:social media|the future|the past|employment|unemployment|healthcare|government|companies|households)\b', re.I)


def countries_in(text):
    return {country for country, pattern in _COUNTRY_PATTERNS if pattern.search(text)}


def topic_for(text):
    # A retirement/pension cause is not a general graduate/hiring claim.
    if SG_AUTHORITY.search(text) and re.search(r'\b(?:CPF|MediSave|MediShield|retirement)\b', text, re.I):
        return 'pensions'
    return next((topic for topic, pattern in TOPICS if re.search(pattern, text, re.I)), 'general')


def scope_for(text, location=None):
    topic = topic_for(text)
    named = countries_in(text)
    if len(named) == 1:
        return next(iter(named)), 'explicit', topic
    if named:
        return None, 'unresolved', topic
    if location and not NON_PLACES.search(location):
        # Even an unrecognised explicit place must block the Singapore default.
        return None, 'unresolved', topic
    if FOREIGN_AUTHORITY.search(text):
        return None, 'unresolved', topic
    # Unknown names in geographic constructions must not trigger the default.
    place = re.search(r'\b(?:in|across|throughout|from)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', text)
    if place and place[1] not in {'October', 'November', 'December', 'January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September'}:
        return None, 'unresolved', topic
    if SG_AUTHORITY.search(text):
        return 'Singapore', 'named_authority', topic
    if topic != 'general' and DOMESTIC.search(text) and not re.search(r'\b(?:worldwide|globally|every country|all countries|overseas|abroad)\b', text, re.I):
        return 'Singapore', 'singapore_default', topic
    return None, 'unresolved', topic


def scoped_query(query, context):
    country = getattr(context, 'jurisdiction', None)
    return f'{country} {query}'[:400] if country and country not in countries_in(query) else query


def scope_guidance(context):
    if not context or not context.jurisdiction:
        return ''
    return (f'The jurisdiction for this check is {context.jurisdiction} '
            f'(basis: {context.jurisdiction_basis}). This is interpretation, not evidence. '
            'Evidence must concern this jurisdiction, not merely be published by a trusted organisation. '
            'Preserve the affected population, effective dates and disputed measurement. '
            'A current rule alone does not establish an alleged future change. '
            'However, an explicitly published rule covering the claimed future period is relevant '
            'to that period. "From YEAR" includes that year, not only years after it. '
            'For a blanket claim about all people or no benefits, an applicable exception can '
            'contradict the blanket statement; it need not describe every member of the group. '
            'Unemployment, underemployment, full-time employment and employment are distinct metrics; '
            'a percentage not in full-time employment is not automatically unemployment. '
            'A claim of doubling needs comparable observations. For an undated claim, apply the disclosed latest-statistics default when supplied. A work-pass minimum is not the actual salary '
            'paid to every foreign worker and cannot alone settle a claim about salary differences.')
