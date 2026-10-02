import pytest


@pytest.fixture(autouse=True)
def isolated_state_dir(tmp_path, monkeypatch):
    """Keep app state out of the real home dir; pre-mark the tour as seen
    (tour tests reset it explicitly)."""
    state_dir = tmp_path / "state"
    monkeypatch.setenv("LOREWRITE_STATE_DIR", str(state_dir))
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "settings.json").write_text('{"tour_seen": true}')
    monkeypatch.setenv("LOREWRITE_DATA_DIR", str(tmp_path / "data"))  # sounds/, ambience/


@pytest.fixture(autouse=True)
def fresh_usage_ledger():
    """The AI spend ledger is a module singleton; isolate it per test."""
    from lorewrite.ai.usage import LEDGER

    LEDGER.clear()
    yield
    LEDGER.clear()
