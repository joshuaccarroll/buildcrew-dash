"""TDD tests for _format_phase_duration (AC-01, AC-14).

Each test calls _format_phase_duration(value) directly and asserts == expected string.
Test vectors are from the spec AC-01.
"""
from buildcrew_dash.screens.kanban import _format_phase_duration


def test_AC01_zero_seconds_returns_lt1m():
    assert _format_phase_duration(0) == "<1m"


def test_AC01_59_seconds_returns_lt1m():
    assert _format_phase_duration(59) == "<1m"


def test_AC01_60_seconds_returns_1m():
    assert _format_phase_duration(60) == "1m"


def test_AC01_90_seconds_returns_1m():
    assert _format_phase_duration(90) == "1m"


def test_AC01_119_seconds_returns_1m():
    assert _format_phase_duration(119) == "1m"


def test_AC01_120_seconds_returns_2m():
    assert _format_phase_duration(120) == "2m"


def test_AC01_3599_seconds_returns_59m():
    assert _format_phase_duration(3599) == "59m"


def test_AC01_3600_seconds_returns_1h00m():
    assert _format_phase_duration(3600) == "1h00m"


def test_AC01_3661_seconds_returns_1h01m():
    assert _format_phase_duration(3661) == "1h01m"


def test_AC01_7200_seconds_returns_2h00m():
    assert _format_phase_duration(7200) == "2h00m"


def test_AC01_negative_returns_lt1m():
    assert _format_phase_duration(-5) == "<1m"
