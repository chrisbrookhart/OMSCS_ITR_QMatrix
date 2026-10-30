# Recorded coding preferences

- Keep generated documentation in `docs_agent/` and preserve human README content.
- Keep source papers and derived extraction records local in ignored `input/` and
  `output/` directories; use synthetic text for shared tests.
- Prefer explicit, focused, typed functions and constants accessed through their
  owning modules. Preserve behavior and verify necessary pipeline fixes.
- Start workbooks with paper index (1–n), experiment index (1–k within each
  paper), citation, linked PDF filename, and abstract. Freeze columns 1–3 only.
  Load filename hyperlinks from local `input/pdf_drive_links.json`; retain plain
  filenames when no link exists. Link changes need only a local workbook export.
  Use BibTeX for all
  bibliographic metadata, with ordinary single columns instead of extraction
  Value / Other / Raw Text triplets. Keep experimental `Other` columns narrow.
- Group experiments by paper, put a representative main experiment first with a
  darker fill, and distinguish additional main studies from supporting checks.
  Use `(same)` for repeated review cells while retaining explicit analysis data.
- Use exactly two alternating paper color families, each with a darker primary
  row and lighter remaining rows. Avoid repeating multicolor column headers.
- Preserve missing values. Report potential reasons separately and label
  hypotheses instead of inventing missing information.
- Papers need not fit every taxonomy category or report every field. Keep
  unreported, inapplicable and unsupported category values blank, with a short
  explanatory cell note. Legitimate gaps are not extraction failures and must not
  trigger invented values or forced category assignments.
- Prefer Luna with max reasoning over Sol for this extraction workload; test
  output-token limits on difficult samples before a full run. Support bounded
  concurrent requests with coordinated checkpoint and workbook writes.
- Support running all papers concurrently with request starts paced to the
  account's observed token-rate limit. Preserve active paid responses when
  changing concurrency, and retain a single coordinator for shared run artifacts.
- Recover complete saved fields before buying another full extraction. Remove
  only identical duplicate roles, keep absent roles unclear, and retain complete
  missing-field notes before truncation. Preserve raw responses and record local
  repairs or targeted retry imports in an explicit audit and review worksheet.
