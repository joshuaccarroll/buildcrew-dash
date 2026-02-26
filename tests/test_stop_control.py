from pathlib import Path
from buildcrew_dash.stop_control import is_stop_pending, request_stop, cancel_stop


def test_is_stop_pending_false_on_fresh_dir(tmp_path):
    result = is_stop_pending(tmp_path)
    assert result is False


def test_request_stop_creates_file_and_dir(tmp_path):
    request_stop(tmp_path)
    assert (tmp_path / ".buildcrew").is_dir()
    assert (tmp_path / ".buildcrew" / ".stop-workflow").is_file()


def test_is_stop_pending_true_after_request(tmp_path):
    request_stop(tmp_path)
    result = is_stop_pending(tmp_path)
    assert result is True


def test_cancel_stop_removes_file(tmp_path):
    request_stop(tmp_path)
    cancel_stop(tmp_path)
    assert not (tmp_path / ".buildcrew" / ".stop-workflow").exists()


def test_cancel_stop_idempotent_no_file(tmp_path):
    cancel_stop(tmp_path)


def test_request_stop_idempotent_double_call(tmp_path):
    request_stop(tmp_path)
    request_stop(tmp_path)
    assert is_stop_pending(tmp_path) is True


def test_round_trip(tmp_path):
    request_stop(tmp_path)
    assert is_stop_pending(tmp_path) is True
    cancel_stop(tmp_path)
    assert is_stop_pending(tmp_path) is False


def test_cancel_stop_returns_none(tmp_path):
    result = cancel_stop(tmp_path)
    assert result is None
