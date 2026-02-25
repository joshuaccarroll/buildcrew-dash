from pathlib import Path

from buildcrew_dash.state_reader import WorkflowState, read

_FIXTURES = Path(__file__).parent / "fixtures/states"


def test_absent_file():
    path = _FIXTURES / "absent.state"
    assert read(path) is None


def test_running_state():
    path = _FIXTURES / "running.state"
    result = read(path)
    assert result is not None
    assert result.task_num == 1
    assert result.total_tasks == 3
    assert result.task_name == "implement the thing"
    assert result.phase == "build"
    assert result.phase_status == "running"
    assert result.invocation_count == 4
    assert result.max_invocations == 15
    assert result.timestamp == 1705312800
    assert result.display_invocation_count == 5
    assert result.auto_mode is True
    # AC-05: confirm return type is WorkflowState dataclass
    assert isinstance(result, WorkflowState) is True
    # AC-06: read() accepts a plain str path
    assert read(str(path)).task_num == 1


def test_complete_state():
    path = _FIXTURES / "complete.state"
    result = read(path)
    assert result is not None
    assert result.task_num == 1
    assert result.total_tasks == 3
    assert result.task_name == "implement the thing"
    assert result.phase == "build"
    assert result.phase_status == "complete"
    assert result.invocation_count == 5
    assert result.max_invocations == 15
    assert result.timestamp == 1705312800
    assert result.display_invocation_count == 5
    assert result.auto_mode is False


def test_missing_auto_mode_defaults_false(tmp_path):
    state_file = tmp_path / "no_auto_mode.state"
    state_file.write_text(
        "task_num=1\n"
        "total_tasks=3\n"
        "task_name=implement the thing\n"
        "phase=build\n"
        "phase_status=running\n"
        "invocation_count=4\n"
        "max_invocations=15\n"
        "timestamp=1705312800\n"
    )
    result = read(state_file)
    assert result is not None
    assert result.auto_mode is False


def test_malformed_line(tmp_path):
    state_file = tmp_path / "test.state"
    state_file.write_text(
        "malformed-no-equals-sign\n"
        "task_num=1\n"
        "total_tasks=3\n"
        "task_name=implement the thing\n"
        "phase=build\n"
        "phase_status=running\n"
        "invocation_count=4\n"
        "max_invocations=15\n"
        "timestamp=1705312800\n"
    )
    result = read(state_file)
    assert isinstance(result, WorkflowState)
    assert result.task_num == 1
    assert result.total_tasks == 3
    assert result.task_name == "implement the thing"
    assert result.phase == "build"
    assert result.phase_status == "running"
    assert result.invocation_count == 4
    assert result.max_invocations == 15
    assert result.timestamp == 1705312800


def test_value_contains_equals(tmp_path):
    # EDGE-03: value may itself contain '='; only the first '=' is the delimiter
    state_file = tmp_path / "equals.state"
    state_file.write_text(
        "task_num=1\n"
        "total_tasks=3\n"
        "task_name=a=b=c\n"
        "phase=build\n"
        "phase_status=running\n"
        "invocation_count=0\n"
        "max_invocations=10\n"
        "timestamp=0\n"
    )
    result = read(state_file)
    assert result is not None
    assert result.task_name == "a=b=c"


def test_comment_and_blank_lines_ignored(tmp_path):
    # EDGE-01/02: comment lines and blank lines are silently skipped
    state_file = tmp_path / "comments.state"
    state_file.write_text(
        "# this is a comment\n"
        "\n"
        "task_num=1\n"
        "total_tasks=3\n"
        "task_name=implement the thing\n"
        "phase=build\n"
        "# another comment\n"
        "\n"
        "phase_status=complete\n"
        "invocation_count=5\n"
        "max_invocations=15\n"
        "timestamp=1705312800\n"
    )
    result = read(state_file)
    assert result is not None
    assert result.task_num == 1
    assert result.phase_status == "complete"


def test_uppercase_keys_normalized(tmp_path):
    # EDGE-06: keys are lowercased so uppercase state files (live .workflow-state format) parse correctly
    state_file = tmp_path / "uppercase.state"
    state_file.write_text(
        "TASK_NUM=2\n"
        "TOTAL_TASKS=5\n"
        "TASK_NAME=uppercase test\n"
        "PHASE=codereview\n"
        "PHASE_STATUS=running\n"
        "INVOCATION_COUNT=1\n"
        "MAX_INVOCATIONS=10\n"
        "TIMESTAMP=1705312800\n"
    )
    result = read(state_file)
    assert result is not None
    assert result.task_num == 2
    assert result.total_tasks == 5
    assert result.task_name == "uppercase test"
    assert result.phase == "codereview"
    assert result.phase_status == "running"
    assert result.display_invocation_count == 2


def test_missing_required_key_raises(tmp_path):
    # MK-01: a state file missing a required key raises KeyError — this is the documented behavior;
    # callers must guarantee well-formed files
    import pytest
    state_file = tmp_path / "incomplete.state"
    state_file.write_text(
        "task_num=1\n"
        "total_tasks=3\n"
        "task_name=implement the thing\n"
        # phase_status intentionally omitted
        "phase=build\n"
        "invocation_count=4\n"
        "max_invocations=15\n"
        "timestamp=1705312800\n"
    )
    with pytest.raises(KeyError):
        read(state_file)


# ---------------------------------------------------------------------------
# PermissionError / FileNotFoundError race condition (ERR-05, ERR-06, EDGE-05)
# ---------------------------------------------------------------------------


def test_permission_error_returns_none(tmp_path):
    """ERR-05/EDGE-05: PermissionError on read_text returns None; file exists so exists() passes."""
    from pathlib import Path as _Path
    from unittest.mock import patch as _patch
    state_file = tmp_path / "perm.state"
    state_file.write_text("task_num=1\n")  # exists, so exists() returns True

    with _patch.object(_Path, "read_text", side_effect=PermissionError("permission denied")):
        result = read(state_file)

    assert result is None


def test_file_not_found_race_condition_returns_none(tmp_path):
    """ERR-06: FileNotFoundError on read_text returns None (race: file deleted after exists() check)."""
    from pathlib import Path as _Path
    from unittest.mock import patch as _patch
    state_file = tmp_path / "race.state"
    state_file.write_text("task_num=1\n")  # exists at check time

    with _patch.object(_Path, "read_text", side_effect=FileNotFoundError("deleted")):
        result = read(state_file)

    assert result is None
