"""The model gateway behind llm/gateway.py, mocked."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Literal

import httpx
import pytest
from pydantic import BaseModel

from benethos_mailbox_agent.errors import (
    AnswerRefusedError,
    ConfigError,
    GatewayUnavailableError,
)
from benethos_mailbox_agent.llm.gateway import Gateway, strict_schema
from fakes import FakeGateway

OTHER = '{"label": "other", "quote": "q", "supplier": null}'


class Inner(BaseModel):
    value: str | None
    quote: str


class Answer(BaseModel):
    label: Literal["invoice", "other"]
    quote: str
    supplier: Inner | None = None


@pytest.fixture
def fake() -> FakeGateway:
    return FakeGateway(model="local-small-q4")


@pytest.fixture
async def gateway(fake: FakeGateway) -> AsyncIterator[Gateway]:
    async with Gateway(
        "https://gateway.example.test/v1/",
        "gateway-key",
        "classifier",
        transport=fake.transport(),
    ) as opened:
        yield opened


async def test_one_call_with_a_schema(fake: FakeGateway, gateway: Gateway) -> None:
    fake.answer({"label": "invoice", "quote": "Ihre Rechnung", "supplier": None})

    reply = await gateway.ask(system="You sort mail.", content="mail", schema=Answer)

    assert reply.value == Answer(label="invoice", quote="Ihre Rechnung")
    assert (reply.model, reply.tokens_in, reply.tokens_out) == (
        "local-small-q4",
        120,
        15,
    )
    (body,) = fake.bodies()
    assert body["model"] == "classifier"
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    assert body["response_format"]["json_schema"]["name"] == "Answer"
    assert "tools" not in body
    assert "temperature" not in body
    request = fake.requests[0]
    assert request.url.path == "/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer gateway-key"


def test_the_strict_schema_closes_every_object() -> None:
    found = strict_schema(Answer)

    assert found["additionalProperties"] is False
    assert found["required"] == ["label", "quote", "supplier"]
    inner = found["$defs"]["Inner"]
    assert inner["additionalProperties"] is False
    assert inner["required"] == ["value", "quote"]


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        '{"label": "maybe", "quote": "x"}',
        '{"quote": "x"}',
    ],
)
async def test_an_answer_outside_the_schema_is_refused(
    fake: FakeGateway, gateway: Gateway, content: str
) -> None:
    fake.answer(content)

    with pytest.raises(AnswerRefusedError) as raised:
        await gateway.ask(system="s", content="c", schema=Answer)

    assert raised.value.reason == "schema"


async def test_an_answer_without_choices_is_refused(
    fake: FakeGateway, gateway: Gateway
) -> None:
    fake.answer(httpx.Response(200, json={"choices": []}))

    with pytest.raises(AnswerRefusedError):
        await gateway.ask(system="s", content="c", schema=Answer)


async def test_an_answer_that_is_no_json_is_refused(
    fake: FakeGateway, gateway: Gateway
) -> None:
    fake.answer(httpx.Response(200, text="<html>"))

    with pytest.raises(AnswerRefusedError):
        await gateway.ask(system="s", content="c", schema=Answer)


@pytest.mark.parametrize("status", [500, 502, 503, 429, 408])
async def test_a_gateway_in_trouble_is_unavailable(
    fake: FakeGateway, gateway: Gateway, status: int
) -> None:
    fake.answer(httpx.Response(status))

    with pytest.raises(GatewayUnavailableError):
        await gateway.ask(system="s", content="c", schema=Answer)


@pytest.mark.parametrize("status", [401, 403, 404])
async def test_a_refused_key_or_alias_is_a_config_error(
    fake: FakeGateway, gateway: Gateway, status: int
) -> None:
    fake.answer(httpx.Response(status))

    with pytest.raises(ConfigError):
        await gateway.ask(system="s", content="c", schema=Answer)


async def test_a_refused_request_is_named(fake: FakeGateway, gateway: Gateway) -> None:
    fake.answer(httpx.Response(400, json={"error": {"message": "too long"}}))

    with pytest.raises(AnswerRefusedError) as raised:
        await gateway.ask(system="s", content="c", schema=Answer)

    assert raised.value.reason == "request"


@pytest.mark.parametrize(
    "failure", [httpx.ConnectError("no"), httpx.ReadTimeout("slow")]
)
async def test_a_gateway_out_of_reach_is_unavailable(
    failure: httpx.TransportError,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise failure

    async with Gateway(
        "https://gateway.example.test/v1",
        "k",
        "m",
        transport=httpx.MockTransport(handler),
    ) as gateway:
        with pytest.raises(GatewayUnavailableError):
            await gateway.ask(system="s", content="c", schema=Answer)


@pytest.mark.parametrize(
    ("url", "allow"),
    [
        ("https://gw.example.com/v1", False),
        ("http://127.0.0.1:4000/v1", False),
        ("http://localhost:4000/v1", False),
        ("http://[::1]:4000/v1", False),
        ("http://gw.example.com/v1", True),
    ],
)
async def test_a_gateway_url_that_keeps_the_key_safe(url: str, allow: bool) -> None:
    async with Gateway(url, "k", "m", allow_http=allow):
        pass


@pytest.mark.parametrize(
    "url", ["http://gw.example.com/v1", "http://10.0.0.5/v1", "ftp://gw/v1", "x"]
)
def test_http_to_another_machine_is_refused(url: str) -> None:
    with pytest.raises(ConfigError, match="MAILBOX_AGENT_GATEWAY"):
        Gateway(url, "k", "m")


async def test_the_alias_stands_in_when_no_model_is_reported(gateway: Gateway) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={"choices": [{"message": {"content": OTHER}}]},
        )
    )
    async with Gateway(
        "https://g.example.test", "k", "alias", transport=transport
    ) as other:
        reply = await other.ask(system="s", content="c", schema=Answer)

    assert (reply.model, reply.tokens_in) == ("alias", 0)
