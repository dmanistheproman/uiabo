"""Discovery and interpretation hints for comparative claims; never verdicts."""

import re

SUPERLATIVE = re.compile(r"\b(?:highest|lowest|largest|smallest|fastest|slowest|tallest|shortest|richest|poorest|best[- ]paid|most[- ](?:paid|expensive|populous))\b", re.I)
POLITICAL_ROLE = re.compile(r"\b(?:prime ministers?|presidents?|politicians?|world leaders?|heads? of government|chancellors?|political leaders?)\b", re.I)
PAY = re.compile(r"\b(?:paid|pay|salar(?:y|ies)|remuneration|compensation)\b", re.I)
WEALTH = re.compile(r"\b(?:wealth|wealthiest|richest|net worth|assets?|business income|private income|total income)\b", re.I)
SALARY_SCOPE = ("This comparison concerns published pay for political office, "
                "not personal wealth or private income. An unqualified national-leader claim is compared "
                "with published global rankings of heads of government. Any explicitly stated comparison "
                "region, population and period must still match. "
                "Published comparisons may omit undisclosed pay and may treat bonuses and allowances differently.")
RANKING_GUIDANCE = """RANKING CLAIMS: A highest/lowest/largest claim needs a comparative
ranking or an explicit same-scope comparison, not just one subject's large salary
or measurement. Preserve geography, time, metric, population and negation. A
unqualified national-leader pay claim ordinarily compares published pay for political office
among heads of government, not personal wealth or private income. Do not replace
an explicitly stated comparison population or region with this default. A credible
explicit ranking can establish that interpreted comparison without enumerating
every country. 'Among the highest' or 'one of the highest' cannot establish 'the
highest'. A proposed pay rise does not establish current actual pay. A dated old
ranking does not automatically establish today's rank; assess its stated period.
No support or contradiction may be inferred from the search wording alone.
"""


def is_ranking(text):
    return bool(SUPERLATIVE.search(text))


def political_salary_ranking(text):
    return bool(is_ranking(text) and POLITICAL_ROLE.search(text) and PAY.search(text) and not WEALTH.search(text))


def ranking_queries(text):
    if not is_ranking(text):
        return []
    topic = " ".join(text.split())[:290]
    focus = "published political office salaries comparison ranking" if political_salary_ranking(text) else "comparative ranking data methodology"
    return [(topic + " " + focus)[:400], (topic + " ranking sources comparison scope date")[:400]]


def ranking_page_priority(claim, title, url, snippet=""):
    if not is_ranking(claim):
        return 0
    text = title + " " + url.replace("-", " ")
    # Ordering only: another country's record can be valuable counterevidence.
    # The semantic stages still check the subject, direction, scope and date.
    score = 2 if SUPERLATIVE.search(text) else 0
    if re.search(r"\brank(?:ing|ings)?\b|\bcompar(?:ison|isons|e)\b", text, re.I):
        score += 1
    if political_salary_ranking(claim) and PAY.search(text):
        score += 1
    return score
