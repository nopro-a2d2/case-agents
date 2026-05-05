"""SessionStore: index sidecar + checkpoint sqlite roundtrip, offline."""

from __future__ import annotations

import json

from case_agent.tui.sessions import SessionStore


def test_touch_creates_index_and_orders_by_recency(tmp_path):
    store = SessionStore(tmp_path)
    store.touch("first", preview="hello")
    store.touch("second", preview="world")
    store.touch("first")  # bump first

    sessions = store.list_sessions()
    names = [s.name for s in sessions]
    assert names == ["first", "second"]
    # preview is preserved when touch() is called without one
    assert sessions[0].preview == "hello"
    store.close()


def test_index_json_is_persisted_human_readable(tmp_path):
    store = SessionStore(tmp_path)
    store.touch("증거인부서", preview="공소장 검토")
    store.close()

    raw = (tmp_path / "sessions" / "index.json").read_text(encoding="utf-8")
    parsed = json.loads(raw)
    assert "증거인부서" in parsed["sessions"]
    assert parsed["sessions"]["증거인부서"]["preview"] == "공소장 검토"


def test_delete_removes_index_entry_and_checkpoint_rows(tmp_path):
    store = SessionStore(tmp_path)
    store.checkpointer.setup()
    store.touch("doomed", preview="x")
    # Insert a fake checkpoint row to verify delete clears it.
    with store._conn:
        store._conn.execute(
            "INSERT INTO checkpoints "
            "(thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, type, checkpoint, metadata) "
            "VALUES (?, '', 'c1', NULL, 'json', X'7b7d', X'7b7d')",
            ("doomed",),
        )
    rows_before = store._conn.execute(
        "SELECT count(*) FROM checkpoints WHERE thread_id=?", ("doomed",)
    ).fetchone()[0]
    assert rows_before == 1

    store.delete("doomed")

    assert "doomed" not in {s.name for s in store.list_sessions()}
    rows_after = store._conn.execute(
        "SELECT count(*) FROM checkpoints WHERE thread_id=?", ("doomed",)
    ).fetchone()[0]
    assert rows_after == 0
    store.close()


def test_corrupt_index_is_treated_as_empty(tmp_path):
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    (sessions_dir / "index.json").write_text("not json", encoding="utf-8")
    store = SessionStore(tmp_path)
    assert store.list_sessions() == []
    store.touch("recover")
    assert {s.name for s in store.list_sessions()} == {"recover"}
    store.close()
