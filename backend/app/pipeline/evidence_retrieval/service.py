from typing import Any, Callable, Optional

EvidenceSearch = Callable[[str], list[dict[str, Any]]]

MIN_RETRIEVAL_SCORE = 0.60


def retrieve_evidence(
    claim_analysis: dict[str, Any],
    search_func: Optional[EvidenceSearch] = None
) -> dict[str, Any]:

    checkable = claim_analysis.get("checkable", False)
    extracted_claim = claim_analysis.get("extracted_claim")

    if not checkable or not extracted_claim:
        return {
            "retrieval_status": "no_evidence",
            "evidence": [],
            "warnings": [
                "The claim is not checkable, so evidence retrieval was skipped."
            ]
        }

    if search_func is None:
        return {
            "retrieval_status": "failed",
            "evidence": [],
            "warnings": [
                "Evidence retrieval has not been connected yet."
            ]
        }

    try:
        results = search_func(extracted_claim)

    except TimeoutError:
        return {
            "retrieval_status": "failed",
            "evidence": [],
            "warnings": [
                "Evidence search could not be completed because the search service timed out."
            ]
        }

    except Exception as error:
        return {
            "retrieval_status": "failed",
            "evidence": [],
            "warnings": [
                f"Evidence search could not be completed: {error}"
            ]
        }

    relevant_results = []

    for evidence in results:
        score = evidence.get("retrieval_score", 0)

        if score >= MIN_RETRIEVAL_SCORE:
            relevant_results.append(evidence)

    relevant_results = _remove_duplicates(relevant_results)

    if not relevant_results:
        return {
            "retrieval_status": "no_evidence",
            "evidence": [],
            "warnings": [
                "No sufficiently relevant evidence was found."
            ]
        }

    return {
        "retrieval_status": "completed",
        "evidence": relevant_results,
        "warnings": []
    }


def _remove_duplicates(
    evidence_list: list[dict[str, Any]]
) -> list[dict[str, Any]]:

    seen_urls = set()
    unique_evidence = []

    for evidence in evidence_list:
        url = evidence.get("url")

        if not url:
            continue

        if url in seen_urls:
            continue

        seen_urls.add(url)
        unique_evidence.append(evidence)

    return unique_evidence
