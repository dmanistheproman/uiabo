# UIABO pipeline infographic

## Open and present

- **UIABO_Pipeline_Infographic.drawio** ? editable two-page file. Open in draw.io / diagrams.net using **File ? Open From ? Device**.
- **Page 1: Pipeline overview** ? six processing stages, provider badges, visible date assumptions and alternative outcomes.
- **Page 2: APIs and model roles** ? service roles, interfaces and the models used.
- **UIABO_Pipeline_Infographic.png** ? page 1, ready to insert into PowerPoint.
- **UIABO_Pipeline_API_Map.png** ? page 2, ready to insert into PowerPoint.
- Matching **SVG** files provide scalable versions for slides.

Both pages are widescreen **16:9**, designed at 1920 ? 1080. PNG exports are 3840 ? 2160. Text, shapes and the five flow arrows are native editable draw.io objects. Each stage and API row is grouped for easier rearrangement.

## Scope

This shows the implemented English-text prototype with web retrieval and semantic assessment, checked against the code on 11 September 2026. It does not present planned image/deepfake or webpage-input features as implemented. The six infographic stages group the code's handoffs for presentation; they are not six independent microservices.

Classification uses **gpt-oss:120b**, **gemma4:31b** and **nemotron-3-super**, with two agreeing category votes required. **gemma4:31b** extracts the claim and expands search queries. **gpt-oss:120b** selects relevant passages and assesses evidence. Final results combine evidence stances and scope checks; there is no three-model truth-verdict vote.

Google Fact Check Tools discovers published fact checks. Tavily performs search and original-page extraction. Firebase Authentication verifies identity, and Cloud Firestore persists private results and allowance updates through the backend. The app calls the project's FastAPI endpoint, **POST /analysis/text**; it does not hold the server's Ollama or retrieval credentials.

The date example illustrates the current-year default for a single unambiguous yearless date. Explicit years, recurring dates and ambiguous date cases are handled separately. The infographic simplifies this behaviour for presentation.

## Implementation references

Relative to `C:\Dev\uiabo`:

- `backend/app/routers/analysis.py` ? authenticated API and result persistence.
- `backend/app/pipeline/orchestration/service.py` ? pipeline order and result assembly.
- `backend/app/pipeline/input_preparation/service.py` ? input validation and normalisation.
- `backend/app/pipeline/claim_analysis/categories.py` and `service.py` ? model choices, voting and extraction.
- `backend/app/pipeline/evidence_retrieval/providers.py`, `enhanced.py`, `query_planning.py`, `relevance.py` ? provider endpoints, discovery and source selection.
- `backend/app/pipeline/evidence_assessment/semantic.py`, `policy.py`, `service.py` ? assessment and aggregation.
- `backend/app/pipeline/shared/dates.py` ? visible current-year assumption.
- `backend/app/auth/dependencies.py` and `backend/app/analyses/store.py` ? identity and storage.

## Editing

Edit the draw.io file directly, then export the selected page from draw.io as SVG or PNG. The supplied previews were generated from the same geometry and text as the editable file; they do not update automatically after manual edits.

`generate_pipeline_infographic.py` regenerates the original files. It requires Python, Pillow, PyMuPDF and Arial fonts at the standard Windows font path. **Back up manual edits first**, because regeneration replaces the diagrams and previews.

The generator checks text widths, text-box heights and page bounds. XML structure, cell references, image dimensions and both rendered previews were checked. `PIPELINE_INFOGRAPHIC_VALIDATION.json` records layout checks.
