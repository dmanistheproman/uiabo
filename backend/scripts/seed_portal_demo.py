"""Seed deterministic demo data for the data-engineer and system-administrator portals.

Creates (or reuses) demo operational accounts and writes clearly-marked
demo documents to Firestore: incorrect-result reports with their assessment
records, analysis pipeline runs, data-ingestion runs, user feedback and a
suspended demo user. Re-running updates timestamps but never duplicates,
and --clean removes everything it created.

Usage (from backend/ with the virtual environment active):

    python -m scripts.seed_portal_demo                    # seed / refresh
    python -m scripts.seed_portal_demo --clean            # remove demo data
    python -m scripts.seed_portal_demo --email me@x.com   # use your account

The script only touches documents whose ids start with the demo_ prefix
(plus the Firebase Auth accounts it creates).
"""

import argparse
import hashlib
from datetime import datetime, timedelta, timezone

from firebase_admin import auth as firebase_auth

from app.firebase import get_firebase_app, get_firestore_client
from app.pipeline.evidence_retrieval.sources import SOURCES

DEMO_EMAIL = "demo.engineer@uiabo.test"
DEMO_PASSWORD = "EngineerDemo2026"
ADMIN_EMAIL = "demo.admin@uiabo.test"
ADMIN_PASSWORD = "AdminDemo2026"
MOBILE_EMAIL = "demo.mobile@uiabo.test"
MOBILE_PASSWORD = "MobileDemo2026"
PREMIUM_EMAIL = "demo.premium@uiabo.test"
PREMIUM_PASSWORD = "PremiumDemo2026"
PLAIN_EMAIL = "demo.plain@uiabo.test"
PLAIN_PASSWORD = "PlainDemo2026"
SUSPENDED_EMAIL = "demo.suspended@uiabo.test"
SUSPENDED_PASSWORD = "SuspendedDemo2026"
FREE_USER_A = "demo_free_user_a"
FREE_USER_B = "demo_free_user_b"
REPORTED_BY = {FREE_USER_A: None, FREE_USER_B: None}

SGT = timezone(timedelta(hours=8))


def hex32(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()[:32]


RESULT_WEATHER = hex32("demo_result_weather")
RESULT_POLICY = hex32("demo_result_policy")
RESULT_NEI = hex32("demo_result_nei")
RESULT_FAILED = hex32("demo_result_failed")

RUN_IDS = [f"demo_run_{index:02d}" for index in range(1, 11)]
REPORT_IDS = ["demo_report_open", "demo_report_reviewing", "demo_report_resolved", "demo_report_dismissed"]
INGESTION_IDS = ["demo_ing_forecast_ok", "demo_ing_forecast_fail", "demo_ing_catalogue_old"]
FEEDBACK_IDS = ["demo_feedback_submitted", "demo_feedback_rating", "demo_feedback_reviewed"]


def mask(uid: str, prefix: str) -> str:
    return f"{prefix}_{hashlib.sha256(uid.encode()).hexdigest()[:10]}"


def days_ago(days: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def evidence_item(evidence_id, publisher, title, stance, quote, url, published="2026-09-30"):
    return {
        "evidence_id": evidence_id, "publisher": publisher, "title": title,
        "stance": stance, "source_type": "government" if "gov" in url else "news",
        "passage": quote, "evidence_quote": quote, "url": url, "published_at": published,
        "retrieval_score": 0.9,
    }


def completed_result(result_id, *, original_text, claim, category, label, score,
                     uncertainty, explanation, evidence, days):
    created = days_ago(days)
    return {
        "result_id": result_id, "processing_status": "completed",
        "original_text": original_text, "extracted_claim": claim,
        "claim_category": category, "checkable": True,
        "concern_label": label, "misinformation_risk_score": score,
        "uncertainty": uncertainty,
        "uncertainty_reasons": ["Evidence agreed on the core facts.",
                                "The risk indicator uses prototype rules; it is not a validated probability."],
        "explanation": explanation,
        "recommended_action": "Read the linked official sources before sharing.",
        "evidence": evidence, "assessment_outcome": "assessed",
        "scoring": None, "warnings": [], "pipeline_version": "sprint-1-v1:retrieval-v2",
        "created_at": created, "saved_at": created,
        "user_id": FREE_USER_A if result_id in (RESULT_WEATHER, RESULT_NEI) else FREE_USER_B,
        "input_type": "text", "request_fingerprint": hashlib.sha256(original_text.encode()).hexdigest(),
        "share_enabled": False,
    }


def demo_results():
    weather_evidence = [
        evidence_item("demo-ev-1", "Ministry of Finance Singapore",
                      "GST and cost-of-living support measures", "contradicts",
                      "No new $500 tax was announced; the release lists existing GST rates and support measures.",
                      "https://www.mof.gov.sg/news-publications/press-releases", "2026-09-28"),
        evidence_item("demo-ev-2", "Reuters",
                      "Singapore budget round-up", "contradicts",
                      "Budget documents contain no reference to a $500 tax starting next week.",
                      "https://www.reuters.com/world/asia-pacific/", "2026-09-29"),
    ]
    policy_evidence = [
        evidence_item("demo-ev-3", "Channel News Asia",
                      "CPF contribution changes from next year", "supports",
                      "CPF employee contribution rates rise by half a percentage point from January.",
                      "https://www.channelnewsasia.com/singapore", "2026-10-01"),
    ]
    return [
        completed_result(RESULT_WEATHER,
            original_text="Forward this: Singapore is introducing a new $500 tax next week, confirm before you get fined.",
            claim="Singapore is introducing a new $500 tax next week",
            category="policy", label="Misleading", score=72, uncertainty="Medium",
            explanation="Official budget releases and news reports contain no such tax; the message matches a known hoax pattern.",
            evidence=weather_evidence, days=5.6),
        completed_result(RESULT_POLICY,
            original_text="My group chat says CPF contribution rates increase by 0.5% from January next year.",
            claim="CPF employee contribution rates increase by 0.5 percentage points from January",
            category="policy", label="Likely Accurate", score=22, uncertainty="Low",
            explanation="A credible national source confirms the contribution-rate change and its start date.",
            evidence=policy_evidence, days=2.4),
        completed_result(RESULT_NEI,
            original_text="Heard the east-side hawker centre is closing for good next month.",
            claim="An east-side hawker centre is closing permanently next month",
            category="other", label="Not Enough Information", score=None, uncertainty="High",
            explanation="No checkable source was found either way; a closure notice has not been published.",
            evidence=[], days=1.2),
    ]


def failed_result():
    created = days_ago(0.8)
    return {
        "result_id": RESULT_FAILED, "processing_status": "failed",
        "original_text": "Viral post claims the reservoir was drained because of a chemical leak.",
        "failure_stage": "evidence_retrieval", "error_code": "RETRIEVAL_UNAVAILABLE",
        "message": "Analysis could not be completed because evidence search is temporarily unavailable.",
        "retryable": True, "warnings": [], "pipeline_version": "sprint-1-v1",
        "created_at": created, "user_id": FREE_USER_B, "input_type": "text",
    }


def report_documents():
    def audit(at, actor, role, action, **extra):
        return {"at": at, "actor_mask": mask(actor, "de"), "actor_role": role,
                "action": action, "note": None, "status_from": None, "status_to": None, **extra}

    created5 = days_ago(5.5)
    open_doc = {
        "report_id": REPORT_IDS[0], "result_id": RESULT_WEATHER, "user_id": FREE_USER_A,
        "user_mask": mask(FREE_USER_A, "usr"), "input_type": "text", "reason": "wrong_label",
        "detail": "The label says Misleading but my aunt works at MOF and says no such tax was ever announced. The message is probably fake, not misleading.",
        "status": "open", "created_at": created5, "updated_at": created5,
        "snapshot": {"claim_category": "policy", "checkable": True, "concern_label": "Misleading",
                     "misinformation_risk_score": 72, "uncertainty": "Medium",
                     "pipeline_version": "sprint-1-v1:retrieval-v2", "result_created_at": created5},
        "review_note": None, "reviewed_by_mask": None, "reviewed_at": None,
        "history": [audit(created5, FREE_USER_A, "user", "created")],
    }
    reviewing_doc = {
        "report_id": REPORT_IDS[1], "result_id": RESULT_POLICY, "user_id": FREE_USER_B,
        "user_mask": mask(FREE_USER_B, "usr"), "input_type": "text", "reason": "wrong_score",
        "detail": "Score of 22 feels too low; the contribution change is real but the 0.5% figure in my chat was exaggerated.",
        "status": "reviewing", "created_at": days_ago(2.3), "updated_at": days_ago(1.1),
        "snapshot": {"claim_category": "policy", "checkable": True, "concern_label": "Likely Accurate",
                     "misinformation_risk_score": 22, "uncertainty": "Low",
                     "pipeline_version": "sprint-1-v1:retrieval-v2", "result_created_at": days_ago(2.4)},
        "review_note": "Quote wording differs from the official release; score range is being checked.",
        "reviewed_by_mask": mask("demo_data_engineer", "de"), "reviewed_at": days_ago(1.1),
        "history": [
            audit(days_ago(2.3), FREE_USER_B, "user", "created"),
            {**audit(days_ago(1.1), "demo_data_engineer", "data_engineer", "status_changed"),
             "status_from": "open", "status_to": "reviewing"},
            audit(days_ago(1.1), "demo_data_engineer", "data_engineer", "note_added"),
        ],
    }
    resolved_doc = {
        "report_id": REPORT_IDS[2], "result_id": hex32("demo_result_hawker"), "user_id": FREE_USER_A,
        "user_mask": mask(FREE_USER_A, "usr"), "input_type": "text", "reason": "wrong_evidence",
        "detail": "The cited article is about a different hawker centre; the one in my message really is closing.",
        "status": "resolved", "created_at": days_ago(4.1), "updated_at": days_ago(3.4),
        "snapshot": {"claim_category": "other", "checkable": True, "concern_label": "Not Enough Information",
                     "misinformation_risk_score": None, "uncertainty": "High",
                     "pipeline_version": "sprint-1-v1:retrieval-v2", "result_created_at": days_ago(4.2)},
        "review_note": "Confirmed the retrieval matched the wrong centre; retrieval query fix tracked separately. Report outcome: confirmed retrieval mismatch.",
        "reviewed_by_mask": mask("demo_data_engineer", "de"), "reviewed_at": days_ago(3.4),
        "history": [
            audit(days_ago(4.1), FREE_USER_A, "user", "created"),
            {**audit(days_ago(3.9), "demo_data_engineer", "data_engineer", "status_changed"),
             "status_from": "open", "status_to": "reviewing"},
            audit(days_ago(3.6), "demo_data_engineer", "data_engineer", "note_added"),
            {**audit(days_ago(3.4), "demo_data_engineer", "data_engineer", "status_changed"),
             "status_from": "reviewing", "status_to": "resolved"},
        ],
    }
    dismissed_doc = {
        "report_id": REPORT_IDS[3], "result_id": RESULT_FAILED, "user_id": FREE_USER_B,
        "user_mask": mask(FREE_USER_B, "usr"), "input_type": "text", "reason": "other",
        "detail": "My check never finished and now the app says the previous check failed.",
        "status": "dismissed", "created_at": days_ago(0.7), "updated_at": days_ago(0.5),
        "snapshot": {"claim_category": "other", "checkable": True, "concern_label": "failed",
                     "misinformation_risk_score": None, "uncertainty": "High",
                     "pipeline_version": "sprint-1-v1", "result_created_at": days_ago(0.8)},
        "review_note": "Not an assessment error: the run failed during a provider outage and the app already offered a retry.",
        "reviewed_by_mask": mask("demo_data_engineer", "de"), "reviewed_at": days_ago(0.5),
        "history": [
            audit(days_ago(0.7), FREE_USER_B, "user", "created"),
            {**audit(days_ago(0.6), "demo_data_engineer", "data_engineer", "status_changed"),
             "status_from": "open", "status_to": "reviewing"},
            audit(days_ago(0.5), "demo_data_engineer", "data_engineer", "note_added"),
            {**audit(days_ago(0.5), "demo_data_engineer", "data_engineer", "status_changed"),
             "status_from": "reviewing", "status_to": "dismissed"},
        ],
    }
    return [open_doc, reviewing_doc, resolved_doc, dismissed_doc]


def demo_pipeline_runs():
    stage_sets = [
        {"input_preparation": 61, "claim_analysis": 2140, "evidence_retrieval": 3480, "evidence_assessment": 2760},
        {"input_preparation": 48, "claim_analysis": 1890, "evidence_retrieval": 2910, "evidence_assessment": 2330},
        {"input_preparation": 55, "claim_analysis": 2460, "evidence_retrieval": 4120, "evidence_assessment": 3180},
        {"input_preparation": 44, "claim_analysis": 1720, "evidence_retrieval": 2640, "evidence_assessment": 2050},
        {"input_preparation": 72, "claim_analysis": 2890, "evidence_retrieval": 4760, "evidence_assessment": 3910},
        {"input_preparation": 39, "claim_analysis": 1680, "evidence_retrieval": 2530, "evidence_assessment": 1990},
    ]
    runs = []
    for index, run_id in enumerate(RUN_IDS):
        stages = stage_sets[index % len(stage_sets)]
        age_days = 6.5 - index * 0.6
        created = days_ago(age_days)
        failed = index == 3  # one mid-window failure
        record = {
            "run_id": run_id, "input_type": "text",
            "created_at": created, "finished_at": created + timedelta(seconds=12),
            "stage_timings_ms": {} if failed else stages,
            "pipeline_version": "sprint-1-v1:retrieval-v2",
            **({"status": "failed", "duration_ms": stages["claim_analysis"] + 640,
                "failure_stage": "claim_analysis", "error_code": "CLAIM_ANALYSIS_FAILED",
                "message": "The claim analysis component failed."}
               if failed else
               {"status": "completed", "duration_ms": sum(stages.values()) + 210}),
        }
        runs.append(record)
    link_created = days_ago(0.9)
    runs.append({
        "run_id": "demo_run_link", "input_type": "link_safety", "status": "completed",
        "created_at": link_created, "finished_at": link_created, "duration_ms": 430,
        "stage_timings_ms": {}, "pipeline_version": "link-safety-v1",
    })
    return runs


def demo_ingestion_runs():
    forecast_dates = ["2026-10-09", "2026-10-10", "2026-10-11", "2026-10-12"]
    fresh = days_ago(0.08)  # ~2 hours ago
    failed = days_ago(1.05)
    stale = days_ago(10)
    return [
        {
            "run_id": INGESTION_IDS[0], "job": "forecast_snapshot", "status": "succeeded",
            "trigger": "manual", "triggered_by_mask": mask("demo_data_engineer", "de"),
            "started_at": fresh, "finished_at": fresh + timedelta(milliseconds=1830),
            "duration_ms": 1830, "items_processed": 4,
            "affected_range": {"forecast_dates": forecast_dates},
            "source": "data.gov.sg NEA/MSS four-day outlook",
            "message": "Snapshot issued 2026-10-08T16:00:00 covers 4 of 4 days.",
            "error_code": None, "follow_ups": [],
        },
        {
            "run_id": INGESTION_IDS[1], "job": "forecast_snapshot", "status": "failed",
            "trigger": "scheduled", "triggered_by_mask": mask("demo_data_engineer", "de"),
            "started_at": failed, "finished_at": failed + timedelta(milliseconds=20),
            "duration_ms": 20, "items_processed": 0, "affected_range": {},
            "source": "data.gov.sg NEA/MSS four-day outlook",
            "message": "Peer certificate verification failed while reaching the provider.",
            "error_code": "FORECAST_UNAVAILABLE",
            "follow_ups": [{"at": days_ago(1.0), "by_mask": mask("demo_data_engineer", "de"),
                            "note": "Provider outage window; re-run manually once the status page clears."}],
        },
        {
            "run_id": INGESTION_IDS[2], "job": "source_catalogue", "status": "succeeded",
            "trigger": "manual", "triggered_by_mask": mask("demo_data_engineer", "de"),
            "started_at": stale, "finished_at": stale + timedelta(milliseconds=95),
            "duration_ms": 95, "items_processed": len(SOURCES),
            "affected_range": {"domains": len(SOURCES)},
            "source": "UIABO trusted-domain allowlist",
            "message": f"Refreshed {len(SOURCES)} trusted sources in the catalogue.",
            "error_code": None, "follow_ups": [],
        },
    ]


def ensure_demo_engineer(db, email, password):
    return _ensure_demo_operational(db, email, password, "Demo Data Engineer", "data_engineer")


def ensure_demo_admin(db, email, password):
    return _ensure_demo_operational(db, email, password, "Demo System Admin", "system_admin")


def _ensure_demo_operational(db, email, password, name, role):
    try:
        user = firebase_auth.create_user(
            email=email, password=password, email_verified=True,
            display_name=name)
        created = True
    except firebase_auth.EmailAlreadyExistsError:
        user = firebase_auth.get_user_by_email(email)
        created = False
    now = datetime.now(timezone.utc)
    db.collection("users").document(user.uid).set({
        "uid": user.uid, "name": name, "email": user.email,
        "email_verified": True, "role": role, "account_status": "active",
        "profile": {}, "storage_used_bytes": 0, "storage_quota_bytes": 0,
        "last_login_at": None, "created_at": now, "updated_at": now,
    }, merge=True)
    return user, created


def ensure_demo_free_user(db, email, password, name, role="free", status="active"):
    """A user account for app testing; free resets daily, premium is monthly."""
    from app.accounts.repository import _new_free_allowance, _new_premium_allowance

    try:
        user = firebase_auth.create_user(
            email=email, password=password, email_verified=True,
            display_name=name)
        created = True
    except firebase_auth.EmailAlreadyExistsError:
        user = firebase_auth.get_user_by_email(email)
        created = False
    now = datetime.now(timezone.utc)
    db.collection("users").document(user.uid).set({
        "uid": user.uid, "name": name, "email": user.email,
        "email_verified": True, "role": role, "account_status": status,
        "profile": {}, "storage_used_bytes": 0, "storage_quota_bytes": 0,
        "last_login_at": None, "created_at": now, "updated_at": now,
    }, merge=True)
    allowance_ref = db.collection("usage_allowances").document(user.uid)
    if not allowance_ref.get().exists:
        allowance = (_new_premium_allowance if role == "premium"
                     else _new_free_allowance)(user.uid, now)
        allowance_ref.set(allowance)
    return user, created


def demo_feedback():
    """Feedback records as a System Administrator would receive them."""
    admin_mask = mask("demo-admin", "de")
    return [
        {
            "feedback_id": FEEDBACK_IDS[0],
            "user_id": FREE_USER_A,
            "category": "general_feedback",
            "rating": None,
            "comments": "The explanation section is really helpful, but the app opens slowly on my older phone.",
            "status": "submitted",
            "created_at": days_ago(6),
            "reviewed_at": None,
            "reviewed_by": None,
        },
        {
            "feedback_id": FEEDBACK_IDS[1],
            "user_id": FREE_USER_B,
            "category": "service_review",
            "rating": 5,
            "comments": "The check flagged a scammy website link my friend sent me. Glad it warned me.",
            "status": "submitted",
            "created_at": days_ago(2),
            "reviewed_at": None,
            "reviewed_by": None,
        },
        {
            "feedback_id": FEEDBACK_IDS[2],
            "user_id": FREE_USER_A,
            "category": "service_review",
            "rating": 4,
            "comments": "Would like to check links in other languages one day.",
            "status": "reviewed",
            "created_at": days_ago(9),
            "reviewed_at": days_ago(7),
            "reviewed_by": admin_mask,
        },
    ]


def write_all(db, email, password):
    user, created = ensure_demo_engineer(db, email, password)
    admin, admin_created = ensure_demo_admin(db, ADMIN_EMAIL, ADMIN_PASSWORD)
    mobile, mobile_created = ensure_demo_free_user(db, MOBILE_EMAIL, MOBILE_PASSWORD, "Demo Mobile User")
    premium, premium_created = ensure_demo_free_user(
        db, PREMIUM_EMAIL, PREMIUM_PASSWORD, "Demo Premium User", role="premium")
    plain, plain_created = ensure_demo_free_user(db, PLAIN_EMAIL, PLAIN_PASSWORD, "Demo Free User")
    suspended, suspended_created = ensure_demo_free_user(
        db, SUSPENDED_EMAIL, SUSPENDED_PASSWORD, "Demo Suspended User", status="suspended")
    writes = []
    for result in demo_results():
        writes.append(("analysis_results", result["result_id"], result))
    writes.append(("analysis_results", RESULT_FAILED, failed_result()))
    for report in report_documents():
        writes.append(("result_reports", report["report_id"], report))
    for run in demo_pipeline_runs():
        writes.append(("pipeline_runs", run["run_id"], run))
    for run in demo_ingestion_runs():
        writes.append(("ingestion_runs", run["run_id"], run))
    for record in demo_feedback():
        writes.append(("feedback", record["feedback_id"], record))
    for collection, document_id, payload in writes:
        db.collection(collection).document(document_id).set(payload)
    return user, created, writes, admin_created, mobile_created or premium_created or plain_created or suspended_created


def clean(db, email):
    removed = 0
    for collection, ids in (
        ("result_reports", REPORT_IDS),
        ("pipeline_runs", [*RUN_IDS, "demo_run_link"]),
        ("ingestion_runs", INGESTION_IDS),
        ("feedback", FEEDBACK_IDS),
        ("analysis_results", [RESULT_WEATHER, RESULT_POLICY, RESULT_NEI, RESULT_FAILED,
                              hex32("demo_result_hawker")]),
    ):
        for document_id in ids:
            db.collection(collection).document(document_id).delete()
            removed += 1
    for demo_email in (email, ADMIN_EMAIL, MOBILE_EMAIL, PREMIUM_EMAIL, PLAIN_EMAIL, SUSPENDED_EMAIL):
        try:
            user = firebase_auth.get_user_by_email(demo_email)
            firebase_auth.delete_user(user.uid)
            db.collection("users").document(user.uid).delete()
            db.collection("usage_allowances").document(user.uid).delete()
            removed += 1
        except firebase_auth.UserNotFoundError:
            pass
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", default=DEMO_EMAIL, help="Demo data-engineer email.")
    parser.add_argument("--password", default=DEMO_PASSWORD,
                        help="Password set when the demo account is first created.")
    parser.add_argument("--clean", action="store_true", help="Remove all demo data instead.")
    args = parser.parse_args()

    get_firebase_app()
    db = get_firestore_client()
    if args.clean:
        removed = clean(db, args.email)
        print(f"Removed {removed} demo documents and the demo auth account ({args.email}).")
        return 0

    user, created, writes, admin_created, free_created = write_all(db, args.email, args.password)
    print(f"Demo engineer account {'created' if created else 'reused'}: {args.email}")
    if created:
        print(f"  password: {args.password}")
    else:
        print("  password unchanged (set at first creation; use Forgot password if needed).")
    print(f"Demo admin account {'created' if admin_created else 'reused'}: {ADMIN_EMAIL}"
          + (f" (password: {ADMIN_PASSWORD})" if admin_created else ""))
    print(f"App accounts {'created' if free_created else 'reused'}: "
          f"{MOBILE_EMAIL} (free), {PREMIUM_EMAIL} (premium), {PLAIN_EMAIL} (free), "
          f"{SUSPENDED_EMAIL} (suspended)")
    print(f"Wrote {len(writes)} demo documents:")
    print(f"  result_reports : {len(REPORT_IDS)} reports across all four statuses")
    print(f"  pipeline_runs  : {len(RUN_IDS)} text runs (incl. 1 failed) + 1 link-safety run")
    print(f"  ingestion_runs : 3 runs (fresh success, failure with follow-up, stale success)")
    print(f"  analysis_results: 4 records backing the reports")
    print(f"  feedback       : {len(FEEDBACK_IDS)} records (2 awaiting review, 1 reviewed)")
    print("\nOpen the portal (http://localhost:5174), log in with the demo account,")
    print("or test the app side: the demo results belong to synthetic users, so report")
    print("submission from the app creates brand-new reports.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
