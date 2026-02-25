from pathlib import Path
from unittest.mock import patch

import pytest

from buildcrew_dash.backlog_reader import read_pending_tasks


# AC-01: missing file returns []
def test_missing_file(tmp_path):
    assert read_pending_tasks(tmp_path) == []


# AC-02: empty file returns []
def test_empty_file(tmp_path):
    (tmp_path / "BACKLOG.md").write_text("", encoding="utf-8")
    assert read_pending_tasks(tmp_path) == []


# AC-03: single pending task returns ["task name"]
def test_single_pending_task(tmp_path):
    (tmp_path / "BACKLOG.md").write_text("- [ ] task name\n", encoding="utf-8")
    assert read_pending_tasks(tmp_path) == ["task name"]


# AC-04: multiple pending tasks returned in file order
def test_multiple_pending_tasks_file_order(tmp_path):
    (tmp_path / "BACKLOG.md").write_text(
        "- [ ] alpha\n- [ ] beta\n- [ ] gamma\n", encoding="utf-8"
    )
    assert read_pending_tasks(tmp_path) == ["alpha", "beta", "gamma"]


# AC-05: [x] and [!] tasks excluded, [ ] included
def test_only_pending_included(tmp_path):
    (tmp_path / "BACKLOG.md").write_text(
        "- [x] done task\n- [!] blocked task\n- [ ] pending task\n",
        encoding="utf-8",
    )
    assert read_pending_tasks(tmp_path) == ["pending task"]


# AC-06: trailing complexity tags stripped
@pytest.mark.parametrize("tag", ["{simple}", "{trivial}", "{standard}"])
def test_trailing_tag_stripped(tmp_path, tag):
    (tmp_path / "BACKLOG.md").write_text(
        f"- [ ] Build auth {tag}\n", encoding="utf-8"
    )
    assert read_pending_tasks(tmp_path) == ["Build auth"]


# AC-07: mid-string braces preserved
def test_mid_string_braces_preserved(tmp_path):
    (tmp_path / "BACKLOG.md").write_text(
        "- [ ] Fix {trivial} issue\n", encoding="utf-8"
    )
    assert read_pending_tasks(tmp_path) == ["Fix {trivial} issue"]


# AC-08: invalid UTF-8 bytes → [] (no exception, no partial list)
def test_invalid_utf8_returns_empty(tmp_path):
    (tmp_path / "BACKLOG.md").write_bytes(b"- [ ] task\n\xff")
    assert read_pending_tasks(tmp_path) == []


# AC-09: case-sensitive tag matching — uppercase not stripped
def test_uppercase_tag_not_stripped(tmp_path):
    (tmp_path / "BACKLOG.md").write_text(
        "- [ ] Build auth {SIMPLE}\n", encoding="utf-8"
    )
    assert read_pending_tasks(tmp_path) == ["Build auth {SIMPLE}"]


# AC-10: pending marker with no content → []
def test_empty_marker_no_content(tmp_path):
    (tmp_path / "BACKLOG.md").write_text("- [ ]\n", encoding="utf-8")
    assert read_pending_tasks(tmp_path) == []


# AC-11: pending marker with spaces only → []
def test_marker_with_spaces_only(tmp_path):
    (tmp_path / "BACKLOG.md").write_text("- [ ]   \n", encoding="utf-8")
    assert read_pending_tasks(tmp_path) == []


# AC-12: OSError on read_text → []
def test_oserror_returns_empty(tmp_path):
    (tmp_path / "BACKLOG.md").write_text("- [ ] task\n", encoding="utf-8")
    with patch.object(Path, "read_text", side_effect=OSError("permission denied")):
        assert read_pending_tasks(tmp_path) == []


# ADV-02: very long task name preserved intact
def test_very_long_task_name(tmp_path):
    name = "a" * 1000
    (tmp_path / "BACKLOG.md").write_text(f"- [ ] {name}\n", encoding="utf-8")
    assert read_pending_tasks(tmp_path) == [name]


# ADV-03: non-allowed tag word not stripped
def test_non_allowed_tag_not_stripped(tmp_path):
    (tmp_path / "BACKLOG.md").write_text("- [ ] Build {complex}\n", encoding="utf-8")
    assert read_pending_tasks(tmp_path) == ["Build {complex}"]


# ADV-04: multiple trailing tags — only the last (end-of-string) tag is stripped
def test_multiple_trailing_tags_only_last_stripped(tmp_path):
    (tmp_path / "BACKLOG.md").write_text(
        "- [ ] Task {simple} {trivial}\n", encoding="utf-8"
    )
    assert read_pending_tasks(tmp_path) == ["Task {simple}"]
