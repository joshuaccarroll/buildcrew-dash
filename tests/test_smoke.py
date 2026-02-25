import pytest
from buildcrew_dash.__main__ import BuildCrewDashApp
from unittest.mock import patch, MagicMock


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_app_launches_and_quits():
    mock_scan = MagicMock(return_value=[])
    with patch("buildcrew_dash.scanner.ProcessScanner.scan", mock_scan):
        async with BuildCrewDashApp().run_test(headless=True) as pilot:
            await pilot.press("q")
