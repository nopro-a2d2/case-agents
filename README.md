# case-agents

Lawyer-facing agent for case-document Q&A, analysis artifacts, and brief drafting,
built on LangChain + Vertex AI with a hand-rolled agent loop.

## Layout

- `case_agent/` — Python package and CLI (`case-agent`).
  - `agent.py` — assembles model, tools, system prompt, and subagents into `CaseAgentComponents`.
  - `loop/` — hand-rolled agent loop (`runner`, `query`, `task_tool`, `strategy_mode`, `headless`).
  - `tools/` — `smart_search`, citation/anchor reader, evidence list, citation/completeness verifiers, calculate, memory, strategy, todos.
  - `subagents/` — explore subagent.
  - `model/` — Vertex AI model + embedder factories.
  - `workspace/` — `LocalFS` workspace abstraction over `data/{case}/`.
  - `prompts/` — main + explore system prompts (markdown).
  - `memory/` — memdir-style memory store.
- `wiki_builder/` — case-wiki compiler (extract → embed → cross-ref → verify).
- `tui-ts/` — Ink/React TUI frontend (Claude Code-style); see `tui-ts/DESIGN.md`.
- `scripts/` — benchmark + eval scripts.
- `tests/` — pytest suite.
- `data/{case}/` — per-case workspace (e.g. `spark`, `spark-v2`).

## Install

```bash
uv sync                 # core deps
uv sync --extra dev     # + pytest, pytest-asyncio
uv sync --extra wiki    # + langfuse for wiki_builder
uv sync --extra s3      # + boto3 (S3 workspace, not yet wired)
```

Requires Python ≥ 3.12 and Google Cloud credentials for Vertex AI.

## CLI

```bash
case-agent run    --case spark "공소장의 핵심 공소사실 3가지를 증거번호와 함께 요약해줘"
case-agent search --case spark "임의제출 절차 위법성" -k 5 --hop 1
case-agent evidence --case spark --person 홍길동 --limit 20
case-agent cite   --case spark "json/1.json#p2"
case-agent verify --case spark drafts/증거인부서_v1.md --kind 증거인부서
case-agent ls     --case spark wiki-output/concepts
```

`--root` overrides the workspace root (default `data`).

## Wiki builder

```bash
python -m wiki_builder --case data/spark-v2          # full pipeline
python -m wiki_builder --case data/spark-v2 --phase 4
```

## TUI (tui-ts)

```bash
cd tui-ts
npm install
npm start          # tsx src/index.tsx
npm run build      # tsc --noEmit
```

## Dev

```bash
pytest
ruff check
```
