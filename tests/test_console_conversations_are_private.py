"""One process serves every technician, so the console store is shared.

It had no notion of whose a conversation was. ``GET /api/claude/conversations``
walked the whole dict and returned every entry to any authenticated caller,
titled with the first eighty characters of what the author typed. The delete
route removed any id. And posting a message with somebody else's
conversation_id — a value the client supplies — both fed its history to the
model and appended to it.

What ends up in there is what a technician types into the console: customer
names, hostnames, whatever they paste while troubleshooting.
"""

from __future__ import annotations

import pytest

from app.services import claude_console as cc


@pytest.fixture(autouse=True)
def clean_store():
    cc._conversations.clear()
    yield
    cc._conversations.clear()


def _seed(cid: str, owner: str, title: str = "t") -> None:
    cc._conversations[cid] = {
        "owner_user_id": owner,
        "messages": [{"role": "user", "content": title}],
        "created_at": "2026-01-01T09:00:00+00:00",
        "title": title,
    }


# ── Listing ──────────────────────────────────────────────────────────────────

def test_a_user_sees_only_their_own():
    _seed("a", "user-1", "Acme FortiGate password reset")
    _seed("b", "user-2", "Bedrift AS tenant migration")
    listed = cc.list_conversations("user-1")
    assert [c["conversation_id"] for c in listed] == ["a"]


def test_the_titles_of_other_users_do_not_leak():
    _seed("b", "user-2", "Bedrift AS admin credentials")
    joined = " ".join(c["title"] for c in cc.list_conversations("user-1"))
    assert "Bedrift" not in joined


def test_an_unowned_entry_belongs_to_nobody():
    # The store does not survive a restart, so this only covers entries
    # written before the owner was recorded. It must not fall to whoever asks.
    cc._conversations["orphan"] = {
        "messages": [], "created_at": "2026-01-01T09:00:00+00:00", "title": "x",
    }
    assert cc.list_conversations("user-1") == []
    assert cc.list_conversations(None) == []


def test_no_user_id_lists_nothing():
    _seed("a", "user-1")
    assert cc.list_conversations(None) == []


# ── Deleting ─────────────────────────────────────────────────────────────────

def test_deleting_your_own_works():
    _seed("a", "user-1")
    assert cc.delete_conversation("a", "user-1") is True
    assert "a" not in cc._conversations


def test_deleting_someone_elses_does_not():
    _seed("b", "user-2")
    assert cc.delete_conversation("b", "user-1") is False
    assert "b" in cc._conversations, "another user's conversation was removed"


def test_a_foreign_id_is_indistinguishable_from_a_missing_one():
    # Both return False, so the route's 404 cannot be used to enumerate which
    # ids exist.
    _seed("b", "user-2")
    assert cc.delete_conversation("b", "user-1") == cc.delete_conversation("nope", "user-1")


# ── Continuing ───────────────────────────────────────────────────────────────

@pytest.fixture
def sdk_mode(monkeypatch):
    """Past the mode and api-key guards, up to the conversation resolve."""
    monkeypatch.setattr(cc, "_get_mode", lambda: "sdk")
    monkeypatch.setattr(cc, "_HAS_ANTHROPIC", True)
    monkeypatch.setattr(cc, "_get_api_key", lambda: "sk-test")


async def _first_event(**kwargs) -> dict:
    async for event in cc.stream_message(**kwargs):
        return event
    raise AssertionError("the generator yielded nothing")


@pytest.mark.asyncio
async def test_posting_into_someone_elses_conversation_is_refused(sdk_mode):
    _seed("b", "user-2")
    event = await _first_event(
        conversation_id="b", message="hei", user_id="user-1",
    )
    assert event["type"] == "error"
    assert len(cc._conversations["b"]["messages"]) == 1, (
        "the message was appended to another user's conversation"
    )


@pytest.mark.asyncio
async def test_your_own_conversation_still_continues(sdk_mode):
    _seed("a", "user-1")
    event = await _first_event(
        conversation_id="a", message="hei", user_id="user-1",
    )
    assert event["type"] == "conversation_id"
    assert len(cc._conversations["a"]["messages"]) == 2


@pytest.mark.asyncio
async def test_a_new_conversation_records_its_owner(sdk_mode):
    event = await _first_event(conversation_id=None, message="hei", user_id="user-1")
    cid = event["conversation_id"]
    assert cc._conversations[cid]["owner_user_id"] == "user-1"
    assert cc.list_conversations("user-1")[0]["conversation_id"] == cid
    assert cc.list_conversations("user-2") == []


# ── The routes pass the identity through ─────────────────────────────────────

def test_the_routes_scope_by_user():
    # The service can only enforce this if the route tells it who is asking;
    # both calls took no user at all before.
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1]
              / "app/web/routes/claude.py").read_text(encoding="utf-8")
    assert "list_conversations(str(user.id))" in source
    assert "delete_conversation(conversation_id, str(user.id))" in source
