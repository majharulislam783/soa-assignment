import importlib.util
import json
import os
import tempfile
from contextlib import closing
from pathlib import Path


spec = importlib.util.spec_from_file_location(
    "notification_consumer", Path(__file__).with_name("consumer.py")
)
consumer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(consumer)


def setup_function():
    handle, database_path = tempfile.mkstemp(suffix=".db")
    os.close(handle)
    consumer.DATABASE_PATH = database_path
    consumer.initialize_database()


def teardown_function():
    os.unlink(consumer.DATABASE_PATH)


def test_consumer_is_idempotent_and_preserves_correlation_id():
    event = {
        "event_id": "evt-123",
        "event_type": "OrderPlaced",
        "occurred_at": "2026-10-20T00:00:00+00:00",
        "correlation_id": "corr-123",
        "order_id": "ord-123",
    }
    body = json.dumps(event).encode()

    first = consumer.process_event(body)
    duplicate = consumer.process_event(body)

    assert first["inserted"] is True
    assert duplicate["inserted"] is False
    with closing(consumer.connect_database()) as connection:
        saved = connection.execute(
            "SELECT correlation_id FROM notification_jobs WHERE event_id = ?",
            ("evt-123",),
        ).fetchone()
    assert saved["correlation_id"] == "corr-123"


def test_consumer_rejects_wrong_event_type():
    body = json.dumps(
        {
            "event_id": "evt-2",
            "event_type": "CustomerDeleted",
            "occurred_at": "2026-10-20T00:00:00+00:00",
            "correlation_id": "corr-2",
            "order_id": "ord-2",
        }
    ).encode()

    try:
        consumer.process_event(body)
    except ValueError as error:
        assert str(error) == "invalid OrderPlaced event"
    else:
        raise AssertionError("wrong event type should be rejected")
