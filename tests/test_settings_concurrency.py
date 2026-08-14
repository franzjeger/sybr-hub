"""Settings are one encrypted blob written by many code paths — safely, now.

Two hazards SR-005 closes:

* Non-atomic writes. `encrypted_write_*` used `path.write_bytes`, so a crash
  mid-write left a truncated settings.json and the next read failed for the
  whole install. Writes now go through the existing atomic helper (temp file,
  fsync, `os.replace`), so an interrupted write leaves the previous file whole.

* Lost updates. Every settings change is read-modify-write. Two concurrent
  changes each loaded the whole dict, edited their field, and saved — and the
  second save dropped the first. `update_app_settings` reads fresh under a lock
  and mutates only the caller's field, so a focused update cannot clobber a key
  another writer set meanwhile.

And the webhook test no longer persists the URL it is testing.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.core import config as cfg
from app.core import encryption as enc

# ── Atomic, interruptible writes ─────────────────────────────────────────────

def test_an_interrupted_write_leaves_the_previous_file_intact(monkeypatch):
    cfg.save_app_settings({"keep": "original"})

    def boom(src, dst):
        raise OSError("simulated crash during replace")

    monkeypatch.setattr("app.core.encryption.os.replace", boom)
    with pytest.raises(OSError):
        cfg.update_app_settings(lambda s: s.__setitem__("keep", "new"))
    monkeypatch.undo()

    assert cfg.load_app_settings() == {"keep": "original"}, "a half-write survived"


def test_an_interrupted_write_leaves_no_temp_file_behind(monkeypatch):
    cfg.save_app_settings({"keep": "original"})
    monkeypatch.setattr(
        "app.core.encryption.os.replace",
        lambda *a: (_ for _ in ()).throw(OSError("boom")),
    )
    with pytest.raises(OSError):
        cfg.save_app_settings({"keep": "new"})
    monkeypatch.undo()

    d = cfg._settings_path().parent
    strays = [p for p in d.iterdir() if p.name.startswith(".settings.json.")]
    assert not strays, f"left temp files: {strays}"


def test_the_public_encrypted_writers_are_atomic(tmp_path, monkeypatch):
    target = tmp_path / "thing.enc"
    enc.encrypted_write_text(target, "v1")
    assert enc.encrypted_read_text(target) == "v1"

    monkeypatch.setattr(
        "app.core.encryption.os.replace",
        lambda *a: (_ for _ in ()).throw(OSError("boom")),
    )
    with pytest.raises(OSError):
        enc.encrypted_write_text(target, "v2")
    monkeypatch.undo()
    assert enc.encrypted_read_text(target) == "v1", "the first value was lost"


def test_bytes_writer_is_atomic_too(tmp_path, monkeypatch):
    target = tmp_path / "b.enc"
    enc.encrypted_write_bytes(target, b"first")
    monkeypatch.setattr(
        "app.core.encryption.os.replace",
        lambda *a: (_ for _ in ()).throw(OSError("boom")),
    )
    with pytest.raises(OSError):
        enc.encrypted_write_bytes(target, b"second")
    monkeypatch.undo()
    assert enc.encrypted_read_bytes(target) == b"first"


# ── Focused updates and serialization ────────────────────────────────────────

def test_a_focused_update_touches_only_its_field():
    cfg.save_app_settings({"a": 1, "b": 2})
    cfg.update_app_settings(lambda s: s.__setitem__("a", 99))
    assert cfg.load_app_settings() == {"a": 99, "b": 2}


def test_interleaved_updates_both_survive():
    cfg.save_app_settings({})
    cfg.update_app_settings(lambda s: s.__setitem__("x", 1))
    cfg.update_app_settings(lambda s: s.__setitem__("y", 2))
    assert cfg.load_app_settings() == {"x": 1, "y": 2}


def test_a_raising_mutator_writes_nothing():
    cfg.save_app_settings({"a": 1})

    def _bad(s):
        s["a"] = 2
        raise ValueError("changed my mind")

    with pytest.raises(ValueError):
        cfg.update_app_settings(_bad)
    assert cfg.load_app_settings() == {"a": 1}, "a failed mutator still wrote"


def test_concurrent_updates_do_not_lose_each_other():
    """The core race: N writers, each setting a distinct key, all survive.

    Before the lock and read-fresh-under-it, each writer loaded the whole dict
    and saved it back, so the last writer's save erased everyone else's key.
    """
    cfg.save_app_settings({})
    N = 40

    def worker(i: int) -> None:
        cfg.update_app_settings(lambda s, i=i: s.__setitem__(f"k{i}", i))

    with ThreadPoolExecutor(max_workers=12) as ex:
        list(ex.map(worker, range(N)))

    final = cfg.load_app_settings()
    missing = [i for i in range(N) if final.get(f"k{i}") != i]
    assert not missing, f"lost {len(missing)} concurrent updates: {missing[:10]}"


def test_concurrent_edits_to_a_shared_counter_are_serialized():
    """Read-modify-write on the *same* field must not race either."""
    cfg.save_app_settings({"n": 0})
    N = 50

    def inc(_i: int) -> None:
        cfg.update_app_settings(lambda s: s.__setitem__("n", s.get("n", 0) + 1))

    with ThreadPoolExecutor(max_workers=12) as ex:
        list(ex.map(inc, range(N)))

    assert cfg.load_app_settings()["n"] == N, "increments were lost to a race"


# ── The webhook test must not persist the URL ────────────────────────────────

@pytest.fixture(autouse=True)
def _reset_middleware_state():
    import app.web.middleware.rate_limit as rl
    from app.web.middleware.auth import _reset_users_exist_cache

    _reset_users_exist_cache()
    rl._hits.clear()
    rl._sensitive_hits.clear()
    yield
    _reset_users_exist_cache()
    rl._hits.clear()
    rl._sensitive_hits.clear()


@pytest.fixture()
async def _init_db(tmp_path):
    import app.core.database as db_mod
    from app.core.database import run_migrations

    db_mod.DB_PATH = tmp_path / "test.db"
    await run_migrations()
    yield


async def test_test_webhook_sends_without_persisting_the_url(_init_db, monkeypatch):
    from fastapi.testclient import TestClient

    from app.core.auth import create_access_token, create_user
    from app.core.rbac import set_can_write
    from app.models.user import Role
    from app.web.server import create_app

    sent: dict = {}

    async def fake_send(url, message):
        sent["url"] = url
        sent["message"] = message
        return True

    monkeypatch.setattr("app.services.webhook_sender.send_simple_message", fake_send)

    # A URL is already stored; the test must not touch it.
    cfg.save_app_settings({"scheduler": {"webhook_url": "https://stored.example/hook"}})

    user = await create_user("boss", "Str0ng-Passphrase-For-Tests!", "Boss", role=Role.admin)
    await set_can_write(user.id, True)
    token = await create_access_token(user)

    with TestClient(create_app()) as client:
        r = client.post(
            "/api/scheduler/test-webhook",
            headers={"Authorization": f"Bearer {token}"},
            json={"webhook_url": "https://typed-in-the-box.example/hook"},
        )

    assert r.status_code == 200, r.text
    # It sent to the supplied URL...
    assert sent["url"] == "https://typed-in-the-box.example/hook"
    # ...and left the stored URL exactly as it was — no persist/restore dance.
    assert cfg.load_app_settings()["scheduler"]["webhook_url"] == "https://stored.example/hook"
