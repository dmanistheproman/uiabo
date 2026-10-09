"""Read only MSS's fixed annual/all-stations maximum; fail closed on changes."""

import asyncio
from datetime import datetime
from html.parser import HTMLParser
import re

from app.pipeline.shared.climate import RECORD_URL, MAX_REFERENCE_AGE, eligible, render_record
from app.pipeline.shared.models import ClimateRecord, EvidenceCandidate, EvidenceProvenance


class _AnnualTable(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = False
        self.tables = 0
        self.rows = []
        self.cell = None
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "table" and "Annual" in dict(attrs).get("class", "").split():
            self.active = True
            self.tables += 1
        if self.active and tag == "tr":
            self.rows.append([])
        if self.active and tag in {"td", "th"}:
            self.cell = []

    def handle_data(self, data):
        self.parts.append(data)
        if self.active and self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if self.active and tag in {"td", "th"} and self.cell is not None:
            self.rows[-1].append(" ".join(" ".join(self.cell).split()))
            self.cell = None
        if tag == "table":
            self.active = False


def parse_record(html, as_of):
    parser = _AnnualTable()
    parser.feed(html)
    if parser.tables != 1 or not parser.rows or parser.rows[0] != ["", "Climate Station", "All Stations"]:
        raise ValueError("MSS annual temperature columns changed")
    rows = [r for r in parser.rows if len(r) == 3 and r[0].startswith("Highest Daily Maximum Temperature")]
    updated = re.findall(r"Updated at\s+(\d{1,2} [A-Za-z]{3} \d{4})", " ".join(parser.parts))
    if len(rows) != 1 or len(updated) != 1 or not re.search(r"[°º]\s*C", rows[0][0]):
        raise ValueError("Missing unambiguous Celsius record or update date")
    maximum = re.match(r"^(\d{2}\.\d+)\s+\D", rows[0][2])
    if not maximum:
        raise ValueError("Missing all-stations temperature")
    data = ClimateRecord(maximum_c=float(maximum[1]), updated_at=datetime.strptime(updated[0], "%d %b %Y").date())
    if not 0 <= (as_of - data.updated_at).days <= MAX_REFERENCE_AGE.days:
        raise ValueError("Historical reference is stale or future dated")
    return data


async def retrieve_record(client, context, dates):
    if not eligible(context, dates):
        return None
    async with asyncio.timeout(6):
        async with client.stream("GET", RECORD_URL, timeout=6, follow_redirects=False) as response:
            response.raise_for_status()
            chunks, size = [], 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > 500_000:
                    raise ValueError("Oversized climate reference")
                chunks.append(chunk)
    data = parse_record(b"".join(chunks).decode("utf-8", errors="strict"), context.as_of)
    passage = render_record(data)
    return EvidenceCandidate(evidence_id="mss-climate-" + data.updated_at.isoformat(),
        title="Singapore historical temperature extremes (all stations)", url=RECORD_URL,
        publisher="Meteorological Service Singapore", source_type="government",
        retrieved_at=context.assessed_at, published_at=data.updated_at,
        passage=passage, climate_record=data, retrieval_score=.9,
        provenance=EvidenceProvenance(source_policy="catalogue", origin_group="gov.sg",
            source_reason="Fixed official MSS annual all-stations temperature table.",
            discovery_method="source_link", relevance="context", relevance_quote=passage,
            relevance_reason="Historical air-temperature context, not a forecast or refutation.",
            applicability="uncertain_time", applicability_reason="Historical record cannot establish future weather."))
