import asyncio
import json
from pathlib import Path

from rootlane_toolbox.broker import Broker
from rootlane_toolbox.models import AgentStep, IncidentDetail
from rootlane_toolbox.stream import event_stream, format_sse
from rootlane_toolbox.store import IncidentStore, now_iso
from tests.conftest import FakeDB

FIXTURE = json.loads(
    (Path(__file__).resolve().parents[2] / "ui" / "fixtures" / "stream-events.json").read_text()
)
SHAPES = {item["event"]: item["data"] for item in FIXTURE}


def _detail(status="investigating"):
    return IncidentDetail.model_validate(
        dict(
            id="inc_01",
            title="Requests served for an identity that never authenticated",
            status=status,
            severity="high",
            category="identity",
            opened_at=now_iso(),
            summary="s",
        )
    )


async def test_subscriber_receives_published_messages_in_order():
    broker = Broker()
    queue = broker.subscribe()
    broker.publish("step", {"n": 1})
    broker.publish("incident_update", {"n": 2})
    assert await asyncio.wait_for(queue.get(), 1) == ("step", {"n": 1})
    assert await asyncio.wait_for(queue.get(), 1) == ("incident_update", {"n": 2})


async def test_slow_subscriber_drops_oldest_and_never_blocks_publishers():
    broker = Broker(maxsize=2)
    queue = broker.subscribe()
    for n in range(5):
        broker.publish("step", {"n": n})
    await asyncio.sleep(0)
    received = [queue.get_nowait()[1]["n"] for _ in range(queue.qsize())]
    assert received == [3, 4]


async def test_unsubscribe_stops_delivery():
    broker = Broker()
    queue = broker.subscribe()
    broker.unsubscribe(queue)
    broker.publish("step", {})
    await asyncio.sleep(0)
    assert queue.empty() and broker.subscriber_count == 0


async def test_publish_from_another_thread_reaches_the_subscriber():
    broker = Broker()
    queue = broker.subscribe()
    await asyncio.to_thread(broker.publish, "step", {"n": 1})
    assert await asyncio.wait_for(queue.get(), 1) == ("step", {"n": 1})


def test_format_sse_is_event_then_data_json():
    assert format_sse("ping", {}) == 'event: ping\ndata: {}\n\n'
    assert format_sse("step", {"a": 1}) == 'event: step\ndata: {"a": 1}\n\n'


async def test_stream_yields_published_events_with_fixture_shapes():
    broker = Broker()
    stream = event_stream(broker, ping_interval_s=30)
    first = asyncio.ensure_future(stream.__anext__())
    await asyncio.sleep(0)
    broker.publish("step", SHAPES["step"])
    broker.publish("incident_update", SHAPES["incident_update"])
    chunks = [await asyncio.wait_for(first, 1), await asyncio.wait_for(stream.__anext__(), 1)]
    await stream.aclose()
    assert chunks[0].startswith("event: step\n")
    assert json.loads(chunks[0].split("data: ")[1]) == SHAPES["step"]
    assert chunks[1].startswith("event: incident_update\n")
    assert json.loads(chunks[1].split("data: ")[1]) == SHAPES["incident_update"]


async def test_stream_sends_ping_when_idle():
    stream = event_stream(Broker(), ping_interval_s=0.01)
    chunk = await asyncio.wait_for(stream.__anext__(), 1)
    await stream.aclose()
    assert chunk == format_sse("ping", {})
    assert SHAPES["ping"] == {}


async def test_closing_the_stream_removes_the_subscriber():
    broker = Broker()
    stream = event_stream(broker, ping_interval_s=0.01)
    await stream.__anext__()
    assert broker.subscriber_count == 1
    await stream.aclose()
    assert broker.subscriber_count == 0


async def test_store_publishes_incident_update_on_create_and_status_change():
    broker = Broker()
    queue = broker.subscribe()
    store = IncidentStore(FakeDB(), broker=broker)
    store.put(_detail())
    event, data = await asyncio.wait_for(queue.get(), 1)
    assert event == "incident_update"
    assert data == {
        "id": "inc_01",
        "status": "investigating",
        "severity": "high",
        "title": "Requests served for an identity that never authenticated",
    }
    assert set(data) == set(SHAPES["incident_update"])


async def test_store_does_not_republish_an_unchanged_status():
    broker = Broker()
    queue = broker.subscribe()
    existing = _detail().model_dump_json()
    store = IncidentStore(FakeDB(responses={"FROM incidents": [[existing]]}), broker=broker)
    store.put(_detail())
    await asyncio.sleep(0)
    assert queue.empty()


async def test_store_publishes_step_when_recorded():
    broker = Broker()
    queue = broker.subscribe()
    existing = _detail().model_dump_json()
    store = IncidentStore(FakeDB(responses={"FROM incidents": [[existing]]}), broker=broker)
    step = AgentStep(ts=now_iso(), kind="query", summary="Pulled 40 requests", outcome="ok")
    store.add_step("inc_01", step)
    event, data = await asyncio.wait_for(queue.get(), 1)
    assert event == "step"
    assert data["incident_id"] == "inc_01" and data["kind"] == "query"
    assert set(data) == set(SHAPES["step"])
