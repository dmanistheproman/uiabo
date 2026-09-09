# UIABO Preliminary User Manual ? implemented features

Use **FYP-26-S3-30_PrelimUserManual_DRAFT.docx**, version 0.2, dated
8 September 2026. The current Word manual covers implemented functions only.

Its structure follows the supplied sample:

1. Introduction
2. The Initial Installation Instructions
3. Key Features of uiabo
4. Initial GUIs of uiabo

The manual has 19 pages, refreshed Word contents/page fields and four actual
Android captures. It covers account access, text checks, result interpretation,
source links, saved history, sharing, profile-name editing, Help and the working
free/Premium text allowances.

- `PUMParts_Implemented/`: five current editable Word section files.
- `assets_implemented/`: the four actual Android captures used in this edition.
- `PUM_UPDATE_SUMMARY.md`: structural mapping and implementation evidence.
- `PUM_MISSING_INFORMATION.md`: documentation gaps kept outside the user manual.
- `PUM_DOCUMENT_VALIDATION.json`: the validation record.
- `build_implemented_pum.py`: Word-only builder for this edition. Requires
  python-docx and docxcompose, the prior installation section and repository
  evaluation captures. Preserve manual edits before rebuilding.

The PDF remains the previous 7 September, 38-page draft and is not the current
implemented-only manual. No PDF was generated for this revision. The older
`PUMParts/`, `assets/` and `build_pum_sections.py` are retained as earlier inputs;
that older builder includes proposed functions and must not be used to regenerate
this edition. Previous Word/notes are backed up locally in `backups/`.

Edit the current combined Word document or current chapter files, keeping copies
consistent. Refresh contents and page fields after edits. The original local
submission folder and the repository copy are not automatically synchronized.
