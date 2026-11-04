"""Bounded discovery plans for imminent public changes, never truth labels."""

from datetime import timedelta
import re


def public_change_plan(text, context, dates):
    if not context or context.input_intent == "hypothetical":
        return None
    if (context.jurisdiction == 'Singapore' and context.input_intent == 'assertion'
            and context.retrieval_topic in {'policing', 'healthcare_subsidies'}
            and context.claim_type == 'policy_change'
            and re.search(r'\bwill\b', text, re.I)
            and not re.search(r'\b(?:could|might|may|discuss\w*|consider\w*|propos\w*|den(?:y|ies|ied))\b', text, re.I)
            and (not dates or dates.start_date and context.as_of <= dates.start_date <= context.as_of + timedelta(days=366))):
        # These are discovery targets, not claims that the announcement is false.
        # A conditional consequence ("fined if...") is not a hypothetical question.
        from ..evidence_retrieval.topic_scope import domains_for, topic_queries
        queries = topic_queries(text, context)
        if queries:
            return dict(kind='policy_change', subject='Singapore ' + context.retrieval_topic.replace('_', ' '),
                        assumption='', domains=domains_for(context), queries=queries, baseline_urls=[])
    if re.search(r"\b(?:not|never|if|unless|could|might|may|discuss|discussing)\b|n['’]t\b", text, re.I):
        return None
    if dates and (not dates.start_date or not dates.end_date
                  or not context.as_of <= dates.start_date <= dates.end_date <= context.as_of + timedelta(days=14)):
        return None
    rest = text.replace(dates.claim_text, "") if dates else text
    airport = re.fullmatch(
        r"(?:the airport|Changi(?: airport)?|Singapore(?:'s)? (?:Changi )?airport)\s+"
        r"(?:will|is going to)\s+(?:close|be closed)\s*[.!?]?\s*"
        r"(?:Everyone needs to change their flights[.!?]?)?", rest.strip(), re.I)
    if airport and dates:
        assumption = ("Interpreted the unnamed airport as Changi Airport in Singapore. "
                      "A named airport or other location takes priority.") if text.lower().startswith("the airport") else ""
        return dict(kind="airport_closure", subject="Changi Airport", assumption=assumption,
            domains=["changiairport.com", "caas.gov.sg", "ica.gov.sg"],
            queries=[f'Changi Airport closure advisory {dates.start_date.strftime("%B %Y")}',
                     f'Changi Airport latest news flight disruption closure {context.as_of.year}'],
            baseline_urls=["https://www.ica.gov.sg/about-ica/about-us/our-checkpoints",
                           "https://www.changiairport.com/en/fly/flight-information.html"])
    passport = re.fullmatch(
        r"ICA will (?:begin|start) rejecting passports with less than (?:one year|1 year|12 months) of validity[.!?]?",
        rest.strip(), re.I)
    if passport:
        return dict(kind="passport_rule", subject="ICA entry requirements for foreign visitors",
            assumption="Interpreted this as an imminent change for foreign visitors entering Singapore, not Singaporeans departing or entering another country.",
            domains=["ica.gov.sg", "ask.gov.sg"],
            queries=[f'ICA passport validity one year new entry requirement official announcement {context.as_of.isoformat()}',
                     f'ICA foreign visitors passport validity current entry requirements {context.as_of.year}'],
            baseline_urls=["https://ask.gov.sg/ica/questions/clos83fvw01lj5k0wp90sbtq5"])
    return None


def official_for_plan(url, plan):
    from urllib.parse import urlparse
    host = (urlparse(str(url)).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in plan["domains"])


def page_priority(plan, title, url, snippet=''):
    if not plan:
        return 0
    if url in plan['baseline_urls']:
        return 4
    if not official_for_plan(url, plan):
        return -1
    text = title + ' ' + url
    if plan['kind'] == 'airport_closure':
        if re.search(r'SG-GEN-0\.3|SG-amdt\.pdf', url, re.I):
            return -2  # Amendment indexes are not the actual closure advisory.
        if re.search(r'hotel|dining|shopping|ratings|design\.', text, re.I):
            return -2
        if re.search(r'no.boarding|passport.less|security-and-baggage|flight-saver|/help/|insurance', text, re.I):
            return 0
        if re.search(r'closure|clos(?:ed|ing)|suspend|disrupt|advisory|/newsroom(?:\.html)?/?$', text, re.I):
            return 3
        if re.search(r'changi-journeys|operating-indicators', text, re.I):
            return 1
        if re.search(r'closure|advis|disrupt|news|operat|flight', text, re.I):
            return 2 if re.search(r'Changi', text+' '+snippet, re.I) else 1
    return 1


def baseline_section(plan, url, text):
    """Keep the literal checkpoint block together, without neighbouring hours.

    The complete page remains available to the assessor. If the known heading
    format changes, leave selection to the normal reader rather than inventing it.
    """
    if (plan and plan['kind'] == 'airport_closure'
            and str(url) == 'https://www.ica.gov.sg/about-ica/about-us/our-checkpoints'):
        match = re.search(r'\*\*Changi Airport\*\*\s+.*?(?=\n\*\*|\Z)', text, re.S)
        if match:
            return match.group().strip()
    return text
