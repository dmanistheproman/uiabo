"""A canonical, quoted rendering of validated official forecast data."""


def render_forecast(data):
    return (
        f"Official air-temperature forecast for {data.location}. "
        f"Issued at {data.issued_at.isoformat()}.\n"
        + "\n".join(
            f"{period.date.isoformat()}: {period.low:g} to {period.high:g} degrees Celsius."
            for period in sorted(data.periods, key=lambda period: period.date)
        )
    )
