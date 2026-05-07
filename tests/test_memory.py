"""Tests for case_agent.memory.memdir."""

from __future__ import annotations

import pytest

from case_agent.memory import (
    MEMORY_DIR,
    MEMORY_INDEX,
    MemoryEntry,
    list_memories,
    read_memory,
    read_memory_index,
    write_memory,
)
from case_agent.workspace import LocalFS


@pytest.fixture
def workspace(tmp_path):
    case_root = tmp_path / "case_x"
    case_root.mkdir()
    return LocalFS(case_id="case_x", root=tmp_path)


def test_write_then_read_round_trip(workspace):
    entry = MemoryEntry(
        name="lawyer_profile",
        description="형사 전문, 평이한 변호인의견서 선호",
        type="user",
        body="전문 분야: 형사. 서면 스타일: 짧은 문장, 결론 먼저.",
    )
    path = write_memory(workspace, entry)
    assert path == f"{MEMORY_DIR}/lawyer_profile.md"

    got = read_memory(workspace, "lawyer_profile")
    assert got.name == entry.name
    assert got.description == entry.description
    assert got.type == "user"
    assert "전문 분야" in got.body


def test_index_updated_after_write(workspace):
    write_memory(
        workspace,
        MemoryEntry(name="m1", description="첫 메모", type="feedback", body="A"),
    )
    write_memory(
        workspace,
        MemoryEntry(name="m2", description="둘째", type="project", body="B"),
    )

    idx = read_memory_index(workspace)
    assert "사건 메모리 인덱스" in idx
    assert f"- [m1]({MEMORY_DIR}/m1.md)" in idx
    assert f"- [m2]({MEMORY_DIR}/m2.md)" in idx
    assert "(feedback)" in idx
    assert "(project)" in idx


def test_index_replaces_existing_entry(workspace):
    write_memory(
        workspace,
        MemoryEntry(name="m1", description="원본", type="user", body="x"),
    )
    write_memory(
        workspace,
        MemoryEntry(name="m1", description="갱신본", type="user", body="y"),
    )
    idx = read_memory_index(workspace)
    # one line for m1, no duplicates
    matches = [ln for ln in idx.splitlines() if ln.startswith("- [m1]")]
    assert len(matches) == 1
    assert "갱신본" in matches[0]
    assert "원본" not in matches[0]


def test_list_memories_sorted(workspace):
    write_memory(
        workspace,
        MemoryEntry(name="zeta", description="z", type="project", body="z"),
    )
    write_memory(
        workspace,
        MemoryEntry(name="alpha", description="a", type="user", body="a"),
    )
    write_memory(
        workspace,
        MemoryEntry(name="beta", description="b", type="feedback", body="b"),
    )
    items = list_memories(workspace)
    assert [(e.type, e.name) for e in items] == [
        ("feedback", "beta"),
        ("project", "zeta"),
        ("user", "alpha"),
    ]


def test_read_memory_index_empty_when_no_writes(workspace):
    assert read_memory_index(workspace) == ""
    assert list_memories(workspace) == []


def test_invalid_type_rejected(workspace):
    with pytest.raises(ValueError):
        write_memory(
            workspace,
            MemoryEntry(name="m1", description="x", type="ethics", body="x"),  # type: ignore
        )


def test_invalid_name_rejected(workspace):
    with pytest.raises(ValueError):
        write_memory(
            workspace,
            MemoryEntry(name="bad/name", description="x", type="user", body="x"),
        )
    with pytest.raises(ValueError):
        write_memory(
            workspace,
            MemoryEntry(name="..", description="x", type="user", body="x"),
        )


def test_frontmatter_round_trip_preserves_body(workspace):
    body = "여러 줄\n본문\n- 불릿\n- 항목"
    write_memory(
        workspace,
        MemoryEntry(name="m1", description="x", type="project", body=body),
    )
    got = read_memory(workspace, "m1")
    assert got.body == body


def test_missing_frontmatter_raises_on_read(workspace):
    workspace.write(f"{MEMORY_DIR}/broken.md", "no frontmatter here\njust text\n")
    with pytest.raises(ValueError):
        read_memory(workspace, "broken")


def test_memory_md_lives_at_workspace_root(workspace):
    write_memory(
        workspace,
        MemoryEntry(name="m1", description="x", type="user", body="x"),
    )
    assert workspace.exists(MEMORY_INDEX)
    assert workspace.exists(f"{MEMORY_DIR}/m1.md")
