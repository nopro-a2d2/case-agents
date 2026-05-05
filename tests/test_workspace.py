"""Smoke tests for the LocalFS workspace against the bundled `spark` case."""

from __future__ import annotations

import pytest

from case_agent.workspace import LocalFS, OutOfWorkspaceError, ReadOnlyError


CASE_ID = "spark"


@pytest.fixture()
def ws() -> LocalFS:
    return LocalFS(case_id=CASE_ID, root="data")


def test_case_root_resolves(ws: LocalFS) -> None:
    assert ws.case_root.name == CASE_ID
    assert (ws.case_root / "wiki-output" / "overview.md").exists()


def test_ls_top_level(ws: LocalFS) -> None:
    entries = ws.ls(".")
    assert "wiki-output" in entries
    assert "cache" in entries
    assert "json" in entries


def test_read_overview(ws: LocalFS) -> None:
    txt = ws.read("wiki-output/overview.md")
    assert len(txt) > 0


def test_read_range(ws: LocalFS) -> None:
    txt = ws.read("wiki-output/overview.md", range=(1, 3))
    assert txt.count("\n") <= 2


def test_glob(ws: LocalFS) -> None:
    files = ws.glob("wiki-output/concepts/*.md")
    assert any(f.endswith(".md") for f in files)
    assert len(files) > 0


def test_grep_regex(ws: LocalFS) -> None:
    matches = list(ws.grep(r"임의제출", path="wiki-output/concepts", max_results=5))
    assert len(matches) > 0
    assert all(m.path.startswith("wiki-output/concepts/") for m in matches)


def test_path_escape_rejected(ws: LocalFS) -> None:
    with pytest.raises(OutOfWorkspaceError):
        ws.read("../../etc/passwd")
    with pytest.raises(OutOfWorkspaceError):
        ws.read("/etc/passwd")


def test_readonly_prefixes(ws: LocalFS) -> None:
    assert ws.is_readonly("wiki-output/overview.md") is True
    assert ws.is_readonly("cache/concept_registry.json") is True
    assert ws.is_readonly("json/1.json") is True
    assert ws.is_readonly("artifacts/foo.md") is False
    assert ws.is_readonly("drafts/bar.md") is False


def test_write_blocked_on_readonly(ws: LocalFS) -> None:
    with pytest.raises(ReadOnlyError):
        ws.write("wiki-output/should_not.md", "x")


def test_write_and_edit_roundtrip(ws: LocalFS, tmp_path) -> None:
    p = "notes/_workspace_smoke.md"
    ws.write(p, "hello\nworld\n")
    assert ws.read(p) == "hello\nworld\n"
    ws.edit(p, "world", "변호사")
    assert "변호사" in ws.read(p)
