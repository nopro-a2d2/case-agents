---
name: timeline_draft
description: Draft a chronological timeline artifact from existing case evidence with citations.
when_to_use: When the user asks for a timeline (연표) and one does not yet exist.
allowed-tools: smart_search, read_with_anchor, list_evidence, write_file, verify_citations
argument-hint: <focus> (e.g. defendant name, period, issue keyword)
---

# Timeline Draft

You were invoked to draft a new timeline artifact.

## Inputs

* `<focus>` — narrow the timeline scope (defendant, period, issue). May be empty;
  in that case use the full case.

## Steps

1. **Gather** — call `smart_search(query=<focus>, k=12, hop=1)` and
   `list_evidence()` to enumerate dated events. Prefer wiki-output and json
   evidence; fall back to sources only when needed.
2. **Order** — sort by absolute date. Resolve relative dates ("그 다음 날") to
   absolute when context permits; otherwise keep them with a `~` prefix.
3. **Cite** — every row carries at least one `path#anchor` citation that
   `verify_citations` will accept.
4. **Write** — `write_file(path="artifacts/timeline_<focus_slug>_v1.md", ...)`
   with this shape:
   ```markdown
   # 연표 — <focus>

   | 일시 | 사건 | 출처 |
   |------|------|------|
   | 2024-03-12 | ... | json/3.json#p4 |
   ```
5. **Verify** — call `verify_citations(path=...)` on the written artifact.
   If failures, fix in-place and re-verify until clean. Do not deliver a
   timeline with failing citations.

## Output

Reply with the artifact path and a one-line summary; do not paste the
table back into chat.
