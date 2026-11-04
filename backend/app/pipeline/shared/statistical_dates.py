"""The disclosed default for undated statistical comparisons, not a truth rule."""
import re

LATEST_STATISTICS_NOTICE = (
    'No comparison dates were given. We interpret this as a recent change and use '
    'the latest comparable statistics found, comparing the newest observation with '
    'the preceding comparable observation. The result states the dates used; '
    'include dates if you meant a different period.'
)


def uses_latest_statistics(text):
    if not re.search(r'\bdoubl\w*|\btripl\w*|\bhalved\b|\b(?:increas\w*|decreas\w*|rose|fell|grew)\s+(?:by\s+)?\d+(?:\.\d+)?\s*(?:%|percent|per cent)', text, re.I):
        return False
    # A stated or historical period takes precedence, even if our date parser
    # cannot resolve it. Never replace a vague explicit interval with a new one.
    clean = re.sub(r'[$£€]\s*\d[\d,.]*|\b(?:SGD|USD|THB)\s*\d[\d,.]*', '', text, flags=re.I)
    return not re.search(
        r'\b(?:19|20|21)\d{2}\b|\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b'
        r'|\bQ[1-4]\b|\b(?:today|yesterday|tomorrow|since|historically|previously|formerly|ago|pandemic|decade|century)\b'
        r'|\b(?:last|past|previous|next|this|that|earlier|following)\s+(?:\w+\s+)?(?:days?|weeks?|months?|quarters?|years?)\b'
        r'|\b(?:over|within|during|between|before|after)\b|\b(?:will|could|might|forecast\w*|predict\w*)\b'
        r'|\b(?:year.on.year|month.on.month|quarter.on.quarter|annually|monthly|quarterly)\b', clean, re.I)


def latest_guidance(text):
    if not uses_latest_statistics(text):
        return ''
    return (LATEST_STATISTICS_NOTICE + ' Use actual observation dates, not publication dates. '
            'Missing dates alone do not make the claim unassessable under this disclosed default. '
            'Keep population, country, measurement and units unchanged. A rate and a count '
            'are different. Do not use forecasts or old observations as current statistics. '
            'A claimed doubling still needs TWO comparable observations, not just the latest value.')
