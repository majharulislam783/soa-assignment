import importlib.util
import json
import os
import tempfile
from contextlib import closing
from pathlib import Path


spec = importlib.util.spec_from_file_location(
    "order_app", Path(__file__).with_name("app.py")
)
order_app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(order_app)


def setup_function():
    handle, database_path = tempfile.mkstemp(suffix=".db")
    os.close(handle)
    order_app.DATABASE_PATH = database_path
    order_app.initialize_database()


def teardown_function():
    os.unlink(order_app.DATABASE_PATH)


def test_order_and_outbox_commit_together():
    request = order_app.PlaceOrderRequest(
        customer_ref="customer-42",
        items=[order_app.OrderItem(sku="lamp-1", quantity=2)],
    )

    order, created = order_app.create_order(request, "corr-123", None)

    assert created is True
    with closing(order_app.connect_database()) as connection:
        saved_order = connection.execute(
            "SELECT status FROM orders WHERE order_id = ?", (order["order_id"],)
        ).fetchone()
        outbox = connection.execute(
            "SELECT event_json FROM outbox WHERE order_id = ?", (order["order_id"],)
        ).fetchone()
    assert saved_order["status"] == "ACCEPTED"
    event = json.loads(outbox["event_json"])
    assert event["event_type"] == "OrderPlaced"
    assert event["correlation_id"] == "corr-123"


def test_idempotency_key_does_not_create_duplicate_order():
    request = order_app.PlaceOrderRequest(
        customer_ref="customer-42",
        items=[order_app.OrderItem(sku="lamp-1", quantity=1)],
    )

    first, created_first = order_app.create_order(request, "corr-1", "request-7")
    second, created_second = order_app.create_order(request, "corr-2", "request-7")

    assert created_first is True
    assert created_second is False
    assert first["order_id"] == second["order_id"]
    assert first["correlation_id"] == second["correlation_id"] == "corr-1"
    with closing(order_app.connect_database()) as connection:
        assert connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] == 1


def test_place_order_handler_returns_accepted_order_and_correlation_id():
    request = order_app.PlaceOrderRequest(
        customer_ref="customer-42",
        items=[order_app.OrderItem(sku="lamp-1", quantity=1)],
    )

    response = order_app.place_order(request, "corr-http-123", "request-http-123")

    assert response["status"] == "ACCEPTED"
    assert response["correlation_id"] == "corr-http-123"
    with closing(order_app.connect_database()) as connection:
        saved = connection.execute(
            "SELECT correlation_id FROM orders WHERE order_id = ?",
            (response["order_id"],),
        ).fetchone()
    assert saved["correlation_id"] == "corr-http-123"
