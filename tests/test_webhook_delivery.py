"""Only a successful HTTP response counts as webhook delivery."""

import httpx
import pytest

from app.services import webhook_sender


@pytest.mark.parametrize("rich", [False, True])
@pytest.mark.parametrize("status", [200, 201, 202, 204, 299, 301, 302, 307, 308, 400, 429, 500])
async def test_delivery_requires_2xx(monkeypatch, rich, status):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(status, headers={"Location": "https://example.com/login"})

    client_class = httpx.AsyncClient
    monkeypatch.setattr(
        webhook_sender.httpx,
        "AsyncClient",
        lambda **kwargs: client_class(transport=httpx.MockTransport(respond), **kwargs),
    )
    url = "https://example.com/webhook"
    if rich:
        delivered = await webhook_sender.send_webhook(
            url, "Audit alert", [{"severity": "warning", "detail": "Example finding"}]
        )
    else:
        delivered = await webhook_sender.send_simple_message(url, "Audit completed")

    assert delivered is (200 <= status < 300)
    # A redirect must not forward the notification to a different endpoint.
    assert len(requests) == 1
