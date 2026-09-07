# UIABO PTD comparison and update — 7 September 2026

## Finding and output

The newly supplied `FYP-26-S2-XX_PrelimTechDocs.pdf` is a 184-page previous-team
real-estate project sample. The requested destination, `Preliminary Technical
Documentation.pdf`, was a different 164-page previous-team diet/nutrition sample,
not a compiled UIABO report. The actual UIABO draft was in `PTDParts/`.

The destination is rebuilt from those UIABO section files, preserving the relevant
requirements, competitor tables, use cases, diagrams, database/UI designs, schedule
figures, roles and historical records. Additional coverage is integrated into those
chapters and Chapters 14–18. The original destination PDF and outdated gap list are
preserved in `backups/`. The real-estate comparison PDF is unchanged.

- **Requested updated PDF:** `Preliminary Technical Documentation.pdf`
- **Editable combined source:** `FYP-26-S3-30_Preliminary_Technical_Documentation.docx`
- **Updated editable sections:** `PTDParts_Updated/` (19 files: cover plus 18 chapters)
- **Original UIABO section files:** `PTDParts/`, retained unchanged, including saved meeting notes
- **Outstanding items:** `PTD_MISSING_INFORMATION.md`

## Comparison with the newly supplied sample

The sample is a coverage reference, not proof that every heading is an assessed
UIABO requirement. Existing UIABO chapter numbering is retained; the following map
shows where each relevant sample topic is addressed.

| Sample topic | Prior UIABO draft | Updated location / treatment |
|---|---|---|
| Cover and document control | Cover existed in section files; no compiled UIABO PDF or current revision record | Correct team cover, dated document control, automatic contents and continuous page numbering |
| 1 Introduction: problem, purpose, vision, objectives | Overview/purpose largely present; explicit vision/objective-evidence mapping missing | 1; 2.5–2.6, with measurable evidence criteria and no invented accuracy target |
| 2.1–2.2 Market research and comparison | Already present in 3–4 | Preserved as the PRD's dated research; no claim of a new market audit |
| 2.3 Conceptualization | Implicit in PRD/overview | 2.7 consolidates rationale from existing scope and design |
| 2.4 SWOT | Missing explicit table | 2.8 adds a labelled draft derived from current strengths, limits and dependencies |
| 2.5 Unique selling point | Value proposition present within business model | 2.9 makes proposed differentiators explicit without claiming market superiority |
| 2.6–2.7 Users/business model | Present | Existing 2.3–2.4 preserved; current tier/feature availability in 1.1 |
| 3 Stakeholders | Names/roles distributed across documents | 2.10 consolidates academic, consumer, operational and provider stakeholders |
| 4 Data sources, types, methods, preprocessing, privacy | Database design existed; current collection method/provenance not documented as a chapter | 14 covers actual request-time Google/Tavily retrieval, catalogue, fields, normalization, privacy gaps and dataset plan |
| 5.1–5.3 Milestones, Gantt, WBS | PRD Gantt images only | 10 retains baseline figures and adds dated milestones, work packages and proposed next priorities |
| 5.4 Project charter | Missing explicit charter | 16 adds a proposed consolidated charter; no fabricated sponsor, approval, budget or signatures |
| 5.5 Communication, escalation, revision protocol | General channels present | 9.3–9.4 adds a proposed communication/escalation/revision process |
| 5.6 Scope statement | Present across PRD/URS but September increment unclear | 1.1, 15.2 and 16.1 distinguish implemented increment, required product and exclusions |
| 6 Requirement definition/gathering/analysis/tools | Use cases present; approach and evidence mapping incomplete | 15 records actual available evidence, priority/hierarchy and traceability; no invented interviews/surveys |
| 7 Functional hierarchy/access/dependencies/I/O | Functional requirements and URS use cases present | 5.1 retained; 6.4 API/contracts; 15.3 hierarchy; 15.4 requirement-to-evidence matrix |
| 8 Non-functional requirements | Present, but targets could read like achievements | 5.2 notes targets; 8.5 and 15.4 record unverified capacity, timings, storage, security and usability |
| 9 Other requirements / privacy / operations | Some security constraints present | 7.1, 14.5 and 16 record controls, operating limits and pending policy/compliance work; no certification asserted |
| 10 Risk management | PRD risk table only | 7 retains baseline ratings and adds observed risks, current mitigation and follow-up responsibility areas |
| 11 Methodology | Already present | 6.1 retained |
| 12 Technical stack, ML, APIs, hosting/deployment | Framework choices present; current provider/app details missing | 6.2 clarified; 6.3–6.6 adds cloud model voting, validation, prompts, retrieval, APIs and local deployment/release gaps |
| 13–15 User stories/use cases/diagrams | Already present as URS facsimiles in 5 | Preserved rather than duplicated; the traceability matrix points back to them |
| 16 Design: DFD, architecture, database, wireframes | Existing TDM material present | Preserved in 5; 5.8 adds current Android captures and 5.9 explains actual owner/transaction/retry design |
| 17 Conclusion | Missing current progress conclusion | 18 summarizes operational completion and unfinished requirements |
| 18 Glossary | Missing | 17 defines UIABO-specific technical and evaluation terms |
| 20 Appendix / sources | References existed; new integration evidence absent | 13 adds implementation references and local artifact locator; 18.2 points to design/test appendices and remaining-work files |

The source sample skips a numbered Section 19. Its numbering defect and its
real-estate content are not copied into UIABO.

## Progress corrections since the earlier draft

- Replaced the stale 154-test/disconnected-pipeline description with the recorded
  **262 passing tests**, successful Android export and focused live Firestore checks.
- Recorded Matthew's cloud model ensemble, failed-vote handling, extraction-span
  validation and the observed 7/8 synthetic claim-stage comparison. This is not
  general detection accuracy.
- Recorded real Google Fact Check/Tavily retrieval and remaining lexical relevance
  and stance limitations. The Great Wall myth-passage error is retained explicitly.
- Added the Android TDM-based Home, text flow, saved result/history captures and
  authenticated owner-bound Firestore persistence.
- Added atomic completion/charging, idempotency, per-user leases, Singapore daily
  free and calendar-month premium counters, and the current history-scaling limit.
- Corrected the current networking description from Axios to fetch and protected
  Firestore access from direct mobile reads to backend API access.
- Distinguished project-granted Premium from paid subscriptions; no checkout,
  renewal or cancellation implementation is claimed.
- Recorded required static-image/deepfake work and excluded audio/video. September's
  basic text increment is distinguished from the full product scope.
- Retained the historical August deepfake discussion with a clear later scope
  clarification, rather than rewriting the meeting as if that decision existed then.
- Added draft learning objectives instead of leaving Section 2.2 blank, and marked
  the project website as not supplied instead of silently leaving Section 9.2 empty.

## Source hierarchy and evidence limits

Primary: UIABO's saved `PTDParts/`, PRD, URS and TDM in the submission folder.
Supplementary: dated MeetingNotes, Sprint 1 handoff/task files, current implementation
and `uiabo/evaluation/reports/` (claim, retrieval, pipeline and app-integration records).
The current PUM provides complementary setup guidance.

Official technical references consulted on 7 September 2026 are listed in Section
13.1: Expo SDK 57, Firebase ID-token verification and transactions, Ollama Cloud,
Google claims.search, Tavily Search and Extract. Existing PRD market references keep
their recorded dates and have not been re-audited here.

SWOT, learning objectives, management procedures, explicit objective criteria and
the charter are draft additions for team review. No participant study, financial
commitment, actual meeting attendance, formal acceptance or individual contribution
percentage has been invented. The exact November deadline is still unknown.

## Editing and reproduction

`update_ptd.py` reads the original saved section files and builds updated copies
and the combined Word source. It does not write into `PTDParts/` or change the
source PDFs. Rerunning it replaces generated files, so preserve subsequent hand
edits first. Use Word to update the combined table of contents/page fields and
export the requested PDF after reviewing layout.

The old `build_ptd_sections.py` is the earlier extraction generator; it is not the
entry point for this progress update. Only saved source content is compiled; an
open Word document's unsaved edits are not represented automatically.
