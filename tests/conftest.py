import pytest


@pytest.fixture(autouse=True)
def isolated_state_dir(tmp_path, monkeypatch):
    """Keep app state out of the real home dir; pre-mark the tour as seen
    (tour tests reset it explicitly)."""
    state_dir = tmp_path / "state"
    monkeypatch.setenv("CHISEL_STATE_DIR", str(state_dir))
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "settings.json").write_text('{"tour_seen": true}')
    monkeypatch.setenv("CHISEL_DATA_DIR", str(tmp_path / "data"))  # sounds/, ambience/


class FakeKeyring:
    """In-memory stand-in for the keyring module (get/set/delete_password)."""

    def __init__(self):
        self.store = {}

    def get_password(self, service, user):
        return self.store.get((service, user))

    def set_password(self, service, user, value):
        self.store[(service, user)] = value

    def delete_password(self, service, user):
        self.store.pop((service, user), None)


@pytest.fixture(autouse=True)
def fake_keyring(monkeypatch):
    """Never touch the real OS keyring: the module-level functions go to a dict."""
    import keyring

    fake = FakeKeyring()
    for name in ("get_password", "set_password", "delete_password"):
        monkeypatch.setattr(keyring, name, getattr(fake, name))
    return fake


@pytest.fixture(autouse=True)
def no_legacy_env(monkeypatch):
    """The deprecated LOREWRITE_* names must not leak in from the developer's shell."""
    monkeypatch.delenv("LOREWRITE_STATE_DIR", raising=False)
    monkeypatch.delenv("LOREWRITE_DATA_DIR", raising=False)


@pytest.fixture(autouse=True)
def fresh_usage_ledger():
    """The AI spend ledger is a module singleton; isolate it per test."""
    from chisel.ai.usage import LEDGER

    LEDGER.clear()
    yield
    LEDGER.clear()
