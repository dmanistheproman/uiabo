"""Split prod's missed decisive claims into extraction vs retrieval failures.

For every gold-decisive claim the prod evidence-v3 run answered "unsure",
check whether any cached page for that claim carries a decisive_* page label
(the labeller read every cached page in full). Decisive page present ->
selection/judging failure; absent -> retrieval pool failure.

Zero API: joins frozen labels v2 against the v3 report rows + page cache.
"""

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "backend/.cache/trial_live_pages_v1.json"
LABELS = ROOT / "evaluation/datasets/trial_v21_live_labels_v2.json"
V3 = ROOT / "evaluation/reports/trial_prod_comparison_v3.json"
REPORT = ROOT / "evaluation/reports/trial_v21_retrieval_audit.json"

ANCHOR = re.compile(r"[$€£]?[\d][\d.,]*[%€£]?|\b(?:19|20)\d{2}\b", re.I)


def anchors(text: str) -> set[str]:
    return {m.group(0) for m in ANCHOR.finditer(text)}


def main() -> int:
    cache = json.loads(CACHE.read_text(encoding="utf-8"))
    pages_by_claim = {r["claim"]: {p["url"]: (p.get("content") or "") for p in r["pages"]}
                      for r in cache["claims"]}
    labels = json.loads(LABELS.read_text(encoding="utf-8"))
    page_labels = {(c["claim"], p["url"]): p["page_label"] for c in labels["claims"] for p in c["pages"]}
    v3 = json.loads(V3.read_text(encoding="utf-8"))

    missed = [r for r in v3["rows"]
              if r["gold"] in ("supporting", "contradicting") and r["verdict"] == "unsure"]
    print(f"gold-decisive claims prod answered unsure: {len(missed)}")

    buckets = {"selection_failure": [], "pool_failure": [], "unclassified": []}
    detail = []
    for row in missed:
        claim = row["claim"]
        pages = pages_by_claim.get(claim, {})
        decisive_urls = [u for u in pages if page_labels.get((claim, u), "").startswith("decisive")]
        entry = {"claim": claim, "gold": row["gold"], "n_pages": len(pages),
                 "decisive_urls": decisive_urls, "bucket": None}
        if decisive_urls:
            bucket = "selection_failure"
        else:
            # no decisive page label: check numeric-anchor coverage as a weak probe
            claim_anchors = anchors(claim)
            hit = any(claim_anchors & anchors(c) for c in pages.values()) if claim_anchors else None
            bucket = "pool_failure" if hit is False else "pool_failure" if hit is None else "pool_failure"
            entry["anchor_pages"] = [u for u, c in pages.items() if claim_anchors & anchors(c)]
        entry["bucket"] = bucket
        buckets[bucket].append(claim)
        detail.append(entry)

    report = {
        "version": "trial-v21-retrieval-audit-v1",
        "missed_decisive": len(missed),
        "summary": {k: len(v) for k, v in buckets.items()},
        "buckets": buckets,
        "detail": detail,
    }
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print("summary:", report["summary"])
    for b in ("selection_failure", "pool_failure"):
        for e in [d for d in detail if d["bucket"] == b][:4]:
            print(f"  [{b}] {e['claim'][:60]} | pages {e['n_pages']} | decisive {[u.split('/')[-1][:28] for u in e['decisive_urls']][:2]}")
    print(f"Report: {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
