---
name: citation_check
description: Verify every `path#anchor` citation in an artifact resolves against the corresponding source files. Surface failures and suggest fixes.
when_to_use: Before delivering any artifact that contains citations.
allowed-tools: verify_citations, read_with_anchor
argument-hint: <artifact_path>
---

# Citation Check

You were invoked to validate citations in a single artifact file.

## Inputs

* `<artifact_path>` — workspace-relative path passed in `args` (e.g. `artifacts/timeline_v1.md`). If empty, ask the user for the path.

## Steps

1. Run `verify_citations(path=<artifact_path>)`. The tool returns a JSON report
   with a per-citation pass/fail list.
2. If `failed > 0`, for each failing token:
   * Call `read_with_anchor` against a *plausible* corrected anchor on the same
     source file (e.g. fix `p1-5` → `p1..5`, or recover the right page range
     from a nearby valid citation).
   * Suggest the corrected `path#anchor` next to the original.
3. Reply with a JSON object:
   ```json
   {
     "ok": <bool>,
     "artifact": "<artifact_path>",
     "total": <int>,
     "failed": [{"original": "...", "reason": "...", "suggested": "..."}, ...]
   }
   ```
   Do not modify the artifact; only diagnose and propose fixes.

## Rules

* Use **only** `verify_citations` and `read_with_anchor`. Do not search or
  draft new prose.
* If the artifact path does not exist, return `{"ok": false, "error": "..."}`.
