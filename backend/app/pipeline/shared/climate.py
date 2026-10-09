"""Versioned prototype policy, not a calibrated weather probability model."""

from datetime import timedelta

RECORD_URL = "https://www.weather.gov.sg/climate-historical-extremes-temperature/"
RULE_VERSION = "sg-temperature-outlier-v1"
MIN_RECORD_GAP_C = 10
OUTLIER_RISK = 85  # Displayed as credibility 15; deliberately a coarse indicator.
MAX_REFERENCE_AGE = timedelta(days=90)
LIMITATION = ("Historical records are not a physical upper limit or a forecast. "
              "This prototype plausibility indicator is not a percentage probability.")


def eligible(context, dates):
    if not (context and context.claim_type == "weather_forecast"
            and context.location and context.location.casefold().strip() == "singapore"
            and context.measurement == "air_temperature"
            and context.input_intent == "assertion" and context.modality == "asserted"
            and dates and dates.start_date and dates.end_date
            and context.as_of <= dates.start_date <= dates.end_date <= context.as_of + timedelta(days=14)):
        return False
    values = [(q.value - 32) * 5 / 9 if q.unit.casefold() in {"f", "fahrenheit"} else q.value
              for q in context.quantities if q.unit.casefold() in {"c", "celsius", "f", "fahrenheit"}]
    # Request budget guard only. The decision uses the fetched record and gap.
    return len(values) == 1 and values[0] >= 45


def render_record(data):
    return (f"Singapore, all stations: highest daily maximum air temperature "
            f"{data.maximum_c:g} degrees Celsius. "
            f"MSS annual historical extremes table updated {data.updated_at.isoformat()}. "
            "This is an observed historical record, not a future forecast.")
