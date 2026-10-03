import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import NotFoundError
from app.models.user import Role, User
from app.services import ai_actions
from app.services import claude_console as cc


@pytest.fixture(autouse=True)
def isolate():
    cc._conversations.clear()
    cc._active_streams.clear()
    ai_actions._pending.clear()
    yield
    cc._conversations.clear()
    cc._active_streams.clear()
    ai_actions._pending.clear()


async def test_tool_loop_uses_selected_model_stops_and_closes_client(monkeypatch):
    calls = []

    class Stream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def __aiter__(self):
            if False:
                yield

        async def get_final_message(self):
            return SimpleNamespace(
                stop_reason="tool_use",
                content=[
                    SimpleNamespace(type="tool_use", name="list_customers", id="tool-1", input={})
                ],
            )

    class Client:
        closed = False

        @property
        def messages(self):
            return self

        def stream(self, **kwargs):
            calls.append(kwargs["model"])
            return Stream()

        async def close(self):
            self.closed = True

    client = Client()
    monkeypatch.setattr(cc, "_get_mode", lambda: "api")
    monkeypatch.setattr(cc, "_get_api_key", lambda: "test-key")
    monkeypatch.setattr(
        "app.core.config.load_app_settings", lambda: {"claude_model": "operator-selected-model"}
    )
    monkeypatch.setattr(cc.anthropic, "AsyncAnthropic", lambda **kwargs: client)
    monkeypatch.setattr(cc, "_dispatch_tool", AsyncMock(return_value=[]))
    events = [e async for e in cc.stream_message(message="hello", user_id="owner")]
    assert calls == ["operator-selected-model"] * cc.MAX_TOOL_ROUNDS
    assert client.closed
    assert any(e["type"] == "error" for e in events)
    assert not cc._active_streams


async def test_action_approval_is_actor_bound_immutable_and_single_use(monkeypatch):
    user = User(
        id="owner",
        username="owner",
        display_name="Owner",
        role=Role.technician,
        can_write=True,
        created_at=datetime.now(UTC),
    )
    other = user.model_copy(update={"id": "other"})
    command = {"host_id": "test-host", "command": "uptime"}
    proposal = ai_actions.propose(user.id, "ssh_execute", command, "customer-a")
    command["command"] = "changed after proposal"
    execute = AsyncMock(return_value={"stdout": "ok"})
    monkeypatch.setattr(cc, "_dispatch_tool", execute)
    with pytest.raises(NotFoundError):
        await ai_actions.decide(proposal["approval_id"], other, approve=True)
    assert execute.await_count == 0
    await ai_actions.decide(proposal["approval_id"], user, approve=True)
    assert execute.call_args.args[1]["command"] == "uptime"
    assert execute.call_args.kwargs == {"approved": True}
    with pytest.raises(NotFoundError):
        await ai_actions.decide(proposal["approval_id"], user, approve=True)
    assert execute.await_count == 1


def test_provider_payload_masks_nested_secrets_and_bounds_output():
    output = json.loads(
        ai_actions.provider_result(
            {"nested": {"api_token": "hidden", "password": "hidden"}, "text": "x " * 100000}
        )
    )
    assert "hidden" not in json.dumps(output)
    assert len(json.dumps(output)) <= 33000


async def test_oversized_message_never_reaches_provider(monkeypatch):
    create = AsyncMock()
    monkeypatch.setattr(cc, "_stream_message_impl", create)
    events = [e async for e in cc.stream_message(message="x" * 16001, user_id="owner")]
    assert events[0]["type"] == "error"
    create.assert_not_called()
