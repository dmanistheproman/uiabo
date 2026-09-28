"""Compare evidence-window selectors by their effect on the duo verdict.

For every decisive labelled page (plus sampled not_decisive/irrelevant
controls), each selector chooses an evidence slice from the cached page;
the slice is scored by the duo (MiniCheck prover + disprover from
TRIAL_DISPROVER). A selector is good when the duo, on its slice, votes the
page label's stance (decisive recall) without opposite-polarity errors.

Zero API spend: pages come from backend/.cache/trial_live_pages_v1.json.
"""

import json
import os
import re
import time
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

from app.pipeline.evidence_retrieval.service import relevance, select_passage
from app.pipeline.trial.nli_engine import NliEngine

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "backend/.cache/trial_live_pages_v1.json"
LABELS = ROOT / "evaluation/datasets/trial_v21_live_labels_v2.json"
REPORT = ROOT / "evaluation/reports/trial_v21_selector_bench.json"

DISPROVER = os.environ.get("TRIAL_DISPROVER", "MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli")
ENTAIL = float(os.environ.get("TRIAL_DUO_ENTAIL", "0.7"))
CONTRA = float(os.environ.get("TRIAL_DUO_CONTRA", "0.9"))
NEUTRAL = float(os.environ.get("TRIAL_DUO_NEUTRAL", "0.5"))
CONTROL_SAMPLE = int(os.environ.get("SELECTOR_CONTROL", "40"))

SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
NUM_DATE = re.compile(r"[$€£\d][\d.,%$€£]*|\b(?:19|20)\d{2}\b", re.I)
CAPS = re.compile(r"\b[A-Z][a-zA-Z'&-]{2,}\b")


def sentences(text: str) -> list[str]:
    return [s for s in SENT_SPLIT.split(re.sub(r"\s+", " ", text[:100000])) if s.strip()]


def cluster(sentences_: list[str], idx: int, radius: int = 1) -> str:
    return " ".join(sentences_[max(0, idx - radius):idx + radius + 1])


def top2_clusters(claim: str, text: str, anchors: bool = False) -> str:
    sents = sentences(text)
    if not sents:
        return ""
    weights = []
    claim_terms = set(re.findall(r"[a-zA-Z$€£\d]{3,}", claim.lower()))
    claim_nums = set(NUM_DATE.findall(claim))
    for i, s in enumerate(sents):
        w = relevance(claim, s)
        if anchors:
            s_nums = set(NUM_DATE.findall(s))
            if claim_nums & s_nums:
                w += 0.30
            if any(t in s.lower() for t in claim_terms if t in (claim_nums and {c.lower() for c in claim_nums} or set())):
                pass
            caps = set(t.lower() for t in CAPS.findall(s))
            if caps & claim_terms:
                w += 0.15
        weights.append((w, i))
    weights.sort(reverse=True)
    picks = [weights[0][1]]
    for _, i in weights[1:]:
        if all(abs(i - j) > 3 for j in picks):
            picks.append(i)
            break
    return " ".join(cluster(sents, i) for i in sorted(picks))


SELECTORS = {
    "prod_slice": lambda c, t: select_passage(c, t),
    "top2_clusters": lambda c, t: top2_clusters(c, t),
    "top2_anchored": lambda c, t: top2_clusters(c, t, anchors=True),
}


def embed_selectors() -> dict:
    """MiniLM cosine top-2 sentence clusters with MMR-style separation."""
    import torch
    from transformers import AutoModel, AutoTokenizer

    name = "sentence-transformers/all-MiniLM-L6-v2"
    tok = AutoTokenizer.from_pretrained(name)
    model = AutoModel.from_pretrained(name)
    model.eval()

    def encode(texts: list[str]) -> "torch.Tensor":
        enc = tok(texts, padding=True, truncation=True, max_length=256, return_tensors="pt")
        with torch.inference_mode():
            out = model(**enc).last_hidden_state
        mask = enc["attention_mask"].unsqueeze(-1)
        return (out * mask).sum(1) / mask.sum(1).clamp(min=1e-9)

    def selector(claim: str, text: str) -> str:
        sents = sentences(text)
        if not sents:
            return ""
        claim_vec = encode([claim])
        vecs = encode(sents)
        sim = (vecs @ claim_vec.T).squeeze(-1)
        first = int(sim.argmax())
        masked = sim.clone()
        masked[first] = -1e9
        for i in range(len(sents)):
            if abs(i - first) <= 2:
                masked[i] = -1e9
        second = int(masked.argmax())
        return " ".join(cluster(sents, i) for i in sorted({first, second}))

    return {"minilm_top2": selector}


def main() -> int:
    load_dotenv(ROOT / ".env", override=False)
    cache = json.loads(CACHE.read_text(encoding="utf-8"))
    content_by_url = {p["url"]: (p.get("content") or "")[:60000]
                      for r in cache["claims"] for p in r["pages"]}
    labels = json.loads(LABELS.read_text(encoding="utf-8"))

    decisive, controls = [], []
    for record in labels["claims"]:
        for page in record["pages"]:
            content = content_by_url.get(page["url"])
            if not content or not content.strip():
                continue
            target = (decisive if page["page_label"].startswith("decisive") else controls)
            target.append({"claim": record["claim"], "label": page["page_label"],
                           "gold": record["gold_claim_verdict"], "content": content})
    import random
    random.seed(21)
    controls = random.sample(controls, min(CONTROL_SAMPLE, len(controls)))
    print(f"decisive pages: {len(decisive)} | controls: {len(controls)}", flush=True)

    selectors = dict(SELECTORS)
    try:
        selectors.update(embed_selectors())
    except Exception as error:  # noqa: BLE001 - selector is optional
        print(f"minilm unavailable: {error}", flush=True)

    ground = NliEngine(model_name="lytang/MiniCheck-DeBERTa-v3-Large")
    disprove = NliEngine(model_name=DISPROVER)
    ground.load()
    disprove.load()
    print(f"duo ready: minicheck + {DISPROVER} (t={ENTAIL}/{CONTRA}/{NEUTRAL})", flush=True)

    rows = []
    for group in ("decisive", "control"):
        items = decisive if group == "decisive" else controls
        for n, item in enumerate(items, 1):
            for name, pick in selectors.items():
                started = time.perf_counter()
                text = pick(item["claim"], item["content"])
                if not text.strip():
                    verdict, chars = "empty", 0
                else:
                    g = ground.predict(text, item["claim"])
                    d = disprove.predict(text, item["claim"])
                    if g.p_supporting >= ENTAIL:
                        verdict = "supporting"
                    elif d.p_contradicting >= CONTRA:
                        verdict = "contradicting"
                    elif d.p_neutral >= NEUTRAL:
                        verdict = "neutral"
                    else:
                        verdict = "abstain"
                    chars = len(text)
                rows.append({"group": group, "claim": item["claim"], "page_label": item["label"],
                             "selector": name, "verdict": verdict, "chars": chars,
                             "seconds": round(time.perf_counter() - started, 2)})
            if n % 20 == 0:
                print(f"[{group} {n}/{len(items)}]", flush=True)

    summary = {}
    for group in ("decisive", "control"):
        for name in selectors:
            sub = [r for r in rows if r["group"] == group and r["selector"] == name]
            n = len(sub)
            if group == "decisive":
                want = {"decisive_supporting": "supporting", "decisive_contradicting": "contradicting"}
                hit = sum(1 for r in sub if r["verdict"] == want.get(r["page_label"]))
                wrong = sum(1 for r in sub if r["verdict"] in
                            ({"decisive_supporting": "contradicting",
                              "decisive_contradicting": "supporting"}[r["page_label"]])
                            for r in [r] if r["verdict"] in ("supporting", "contradicting"))
                abstain = sum(1 for r in sub if r["verdict"] in ("neutral", "abstain", "empty"))
                summary[f"{name}"] = {"decisive_n": n, "correct": hit, "abstained": abstain,
                                      "wrong_polarity": wrong - wrong,  # computed below
                                      "mean_chars": round(sum(r["chars"] for r in sub) / n)}
                # correct the wrong count properly
                w = sum(1 for r in sub
                        if r["verdict"] == {"decisive_supporting": "contradicting",
                                            "decisive_contradicting": "supporting"}[r["page_label"]])
                summary[name]["wrong_polarity"] = w
            else:
                false_decisive = sum(1 for r in sub if r["verdict"] in ("supporting", "contradicting"))
                summary.setdefault(name, {})["control_n"] = n
                summary[name]["false_decisive"] = false_decisive
                summary[name]["mean_chars_control"] = round(sum(r["chars"] for r in sub) / n)

    report = {"version": "trial-v21-selector-bench-v1", "disprover": DISPROVER,
              "duo_thresholds": [ENTAIL, CONTRA, NEUTRAL], "summary": summary, "rows": rows}
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print("\n== selector bench ==")
    for name, s in summary.items():
        print(f"  {name:<14} decisive {s['correct']}/{s['decisive_n']} "
              f"abstained {s['abstained']} wrong_polarity {s['wrong_polarity']} "
              f"chars~{s['mean_chars']} | false_decisive {s['false_decisive']}/{s['control_n']}")
    print(f"Report: {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
