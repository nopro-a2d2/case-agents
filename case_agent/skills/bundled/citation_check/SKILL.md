---
name: citation_check
description: Verify every `@@[id]` citation in an artifact resolves against the corresponding source files. Surface failures and suggest fixes.
when_to_use: Before delivering any artifact that contains citations.
allowed-tools: verify_citations, read_evidence
argument-hint: <artifact_path>
---

# Citation Check

You were invoked to validate citations in a single artifact file.

## Inputs

* `<artifact_path>` — workspace-relative path passed in `args` (e.g. `artifacts/timeline_v1.md`). If empty, ask the user for the path.

## Steps

1. Run `verify_citations(path=<artifact_path>)`. The tool returns a JSON report
   with a per-citation pass/fail list.
2. If `failed > 0`, for each failing token (an `@@[id]` whose id is not
   in the workspace evidence registry):
   * Call `list_evidence(name_contains=...)` or `smart_search` to find the
     intended document and recover its real `id` from the result.
   * Suggest the corrected `@@[id]` next to the original.
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

* Use **only** `verify_citations` and `read_evidence`. Do not search or
  draft new prose.
* If the artifact path does not exist, return `{"ok": false, "error": "..."}`.
