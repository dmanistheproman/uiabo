# UIABO updated Preliminary Technical Documentation

The requested output is **Preliminary Technical Documentation.pdf**.
The editable combined source is
**FYP-26-S3-30_Preliminary_Technical_Documentation.docx**.

- `PTDParts_Updated/`: cover and 18 updated editable chapters.
- `PTDParts/`: original saved UIABO section drafts, retained unchanged.
- `PTD_UPDATE_SUMMARY.md`: comparison with the new sample and a map of additions.
- `PTD_MISSING_INFORMATION.md`: remaining evidence, implementation and decisions.
Previous-team samples, the legacy builder and pre-update backups remain in the
original local submission folder and are excluded from this repository.

The original target PDF was a diet/nutrition sample. The replacement compiles the
UIABO sections and records current progress without claiming unfinished features
or evaluation as completed.

`update_ptd.py` reproduces updated copies and the combined Word document from the
original saved `PTDParts/`. Preserve any later edits before rebuilding. After Word
edits, update the contents/page fields and export a fresh PDF. The older
`build_ptd_sections.py` is not the entry point for this updated compilation.

Document validation: the updated PDF has **177 pages**, no empty pages, refreshed
contents/page fields and correct UIABO identifiers. The combined source retains
all original design media and includes three current Android captures (136 image
placements overall). Representative pages were rendered and inspected. Provider
credential scanning passed. See `PTD_DOCUMENT_VALIDATION.json` for the record.
