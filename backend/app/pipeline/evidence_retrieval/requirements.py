"""Use validated verification obligations as discovery hints, never evidence."""

import re


def clean_queries(queries, limit=2):
    """Bound generated queries and discard URL/provider instructions."""
    result, seen = [], set()
    for query in queries:
        if not isinstance(query, str):
            continue
        query = ' '.join(query.split())[:400]
        if not query or re.search(r'https?://|\b(?:site|filetype):|[\x00-\x1f]', query, re.I):
            continue
        identity = query.casefold()
        if identity not in seen:
            seen.add(identity)
            result.append(query)
        if len(result) >= limit:
            break
    return result


def plan_queries(plan):
    """Give each material assertion a first search before its second wording."""
    if not plan or getattr(plan, 'status', None) != 'planned':
        return []
    assertions = [a for a in plan.assertions if a.material]
    return clean_queries([a.queries[i] for i in range(2) for a in assertions
                          if len(a.queries) > i], limit=10)


def questions(plan):
    if not plan or getattr(plan, 'status', None) != 'planned':
        return []
    return [question for a in plan.assertions if a.material
            for question in a.evidence_questions][:12]


def focus_text(claim, plan=None, queries=()):
    return '\n'.join([claim, *questions(plan), *clean_queries(queries, limit=2)])[:6000]


def methodology_document(title, url=''):
    return bool(re.search(r'\btechnical[ _-]+note\b|\bmethodolog\w*\b|\bdefinitions?\b|\bconcepts?[ _-]+and[ _-]+definitions?\b',
                          (title + ' ' + str(url)).replace('_', ' '), re.I))


def document_priority(claim, item, plan=None, queries=()):
    """Prefer observations over methodology when looking for a measured fact."""
    focus = focus_text(claim, plan, queries)
    numeric = bool(plan and any(a.material and a.kind == 'comparison' for a in plan.assertions)) or bool(
        re.search(r'\bdoubl\w*|\b(?:increas|decreas|rise|risen|fell|fallen|statistics|rates?|counts?|figures)\b', focus, re.I))
    if not numeric or re.search(r'\b(?:define|definition|methodology|how measured)\b', ' '.join(queries), re.I):
        return 0
    if methodology_document(item.get('title',''), item.get('url','')):
        return -2
    return 0
