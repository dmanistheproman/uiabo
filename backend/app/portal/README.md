# Operational portal backend (data engineer)

FastAPI implementation behind the UIABO operational portal. The data-engineer
role investigates user-reported incorrect results (UC-41, UC-42) and monitors
analysis and data-ingestion runs (UC-43). System-administrator pages are a
separate workstream; the shared role gate lives here.

## Package layout

```text
app/portal/
|-- dependencies.py   # require_role() access gate + OperationalContext
|-- models.py         # Pydantic contracts for reports and monitoring views
|-- repository.py     # result_reports storage (Firestore + in-memory)
|-- service.py        # masking, report construction and review updates
app/ingestion/
|-- repository.py     # ingestion_runs storage (Firestore + in-memory)
|-- service.py        # forecast-snapshot and source-catalogue jobs
app/pipeline/orchestration/run_recorder.py  # pipeline_runs storage
```

## Role-gated access

`require_role(*roles)` builds a FastAPI dependency used by every `/portal`
route. It resolves the Firestore profile for the verified ID token and enforces:

- the profile role is one of the named roles (`data_engineer`, `system_admin`);
- `account_status` is `active`;
- suspended, deleted, unverified, wrong-role and missing profiles are all
  denied with a generic 403 that does not reveal which check failed.

Strict separation: `/portal` routes accept `data_engineer` only. Ordinary
users cannot reach operational functions, and `PUT /account/me` never changes
an existing role, so self-promotion is impossible.

## API endpoints

### User side (mobile app / any client)

| Endpoint | Purpose |
| --- | --- |
| `POST /analysis/results/{result_id}/report` | Report a completed text check as incorrect. Body: `reason` (`wrong_label`, `wrong_score`, `wrong_evidence`, `other`) + `detail` (1–2000 chars). Returns 201 with the report id; 409 when an open/reviewing report already exists for the result; 422 for failed or non-text results. |

### Portal side (all require an active `data_engineer` account)

| Endpoint | Purpose |
| --- | --- |
| `GET /portal/reports/summary?from=&to=` | Dashboard aggregates (UC-41): totals, status/label/input-type/pipeline-version breakdowns, per-day trend (Singapore dates). |
| `GET /portal/reports?status=&from=&to=&limit=&cursor=` | Newest-first report list with filters and cursor pagination. |
| `GET /portal/reports/{report_id}` | Investigation view (UC-42): report + associated assessment (claim, label, score, explanation, evidence, warnings) with the user masked. `result_missing` flags a deleted result. |
| `PATCH /portal/reports/{report_id}` | Record an investigation note and/or status change (`open → reviewing → resolved/dismissed`). Every change is appended to the report history (audit trail). |
| `GET /portal/runs?status=&from=&to=&limit=&cursor=` | Analysis-request runs (text pipeline and link safety), newest first. |
| `GET /portal/runs/summary?from=&to=` | Run counts, average and p95 duration, failures by stage, per-day trend. |
| `GET /portal/runs/{run_id}` | One run with per-stage timings and failure details. |
| `GET /portal/ingestion-runs?job=&status=` | Data-ingestion runs plus derived per-job health (`healthy`, `stale`, `failing`, `never_run`). |
| `POST /portal/ingestion-jobs/{job}/run` | Authorised recovery action: run `forecast_snapshot` or `source_catalogue` now. |
| `GET /portal/ingestion-runs/{run_id}` | Run detail with error, provenance and affected data range. |
| `POST /portal/ingestion-runs/{run_id}/follow-up` | Record a follow-up issue against a run (UC-43 flow 7). |

Analysis runs and ingestion runs are separate collections with different
shapes, and the portal labels them separately, so the two are never confused.

## Firestore collections

| Collection | Writer | Contents |
| --- | --- | --- |
| `result_reports` | report endpoint / portal | `report_id`, `result_id`, `user_id` (kept for dedupe; never returned), `user_mask`, `reason`, `detail`, `status`, `snapshot` (label, category, score, uncertainty, pipeline version, result time), `review_note`, `reviewed_by_mask`, `history[]` audit entries. |
| `pipeline_runs` | orchestrator + link-safety router | `run_id` (= result id), `input_type`, `status` (`completed`/`failed`), `created_at`, `finished_at`, `duration_ms`, `stage_timings_ms`, `failure_stage`, `error_code`, `pipeline_version`. **No user content is stored here.** |
| `ingestion_runs` | ingestion service | `run_id`, `job`, `status` (`running`/`succeeded`/`incomplete`/`failed`), `trigger`, `started_at`/`finished_at`/`duration_ms`, `items_processed`, `affected_range`, `source`, `message`, `error_code`, `follow_ups[]`. |
| `forecast_snapshots/latest` | forecast job | Validated NEA/MSS four-day outlook snapshot (`issued_at`, periods, `fetched_at`). |
| `source_catalogue/{domain}` | catalogue job | `domain`, `publisher`, `source_type`, `updated_at` — the operational copy of the trusted-domain allowlist. |

Query strategy matches the existing repositories: at most one equality or
range filter runs server side (the prototype project has no composite-index
admin), sorting and extra filters are applied in memory, and cursor pagination
follows the `(created_at, id)` pattern used by `analysis_results`. The index
definitions in `firestore.indexes.json` document the composite indexes that a
production deployment would enable.

## Privacy model

- User content (message, claim, evidence) stays in `analysis_results` and is
  only exposed through the report-investigation endpoint, which requires the
  data-engineer role and returns a masked user id instead of the uid.
- Masks are `sha256(uid)[:10]` with a `usr_`/`de_` prefix: stable for joining
  views, not reversible without the uid.
- `pipeline_runs` and `ingestion_runs` never contain submitted text or URLs.

## Provisioning test accounts

Operational accounts are created by a system administrator (UC-36
pre-condition). Until that portal page exists, use:

```bash
cd backend
python -m scripts.create_operational_account --email engineer@example.com --role data_engineer
```

The Firebase Auth user must already exist (register once in the app), and the
email must be verified for portal access.

## Tests

```bash
cd backend
.venv/bin/python -m pytest tests/portal -q          # role gate, reports, monitoring
.venv/bin/python -m pytest tests/pipeline/orchestration/test_run_monitoring.py -q
.venv/bin/python -m pytest -q                        # full suite
```

All portal tests use in-memory repositories, so no Firebase project is needed.
