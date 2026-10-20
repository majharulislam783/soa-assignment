import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from contextlib import asynccontextmanager, closing
from datetime import datetime, timezone

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field


DATABASE_PATH = os.getenv("ORDER_DB_PATH", "orders.db")
AMQP_URL = os.getenv("AMQP_URL", "amqp://guest:guest@localhost:5672/%2F")
POLL_INTERVAL = float(os.getenv("OUTBOX_POLL_INTERVAL", "1"))
QUEUE_NAME = "order.placed"
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(message)s")
logger = logging.getLogger("order-service")


class OrderItem(BaseModel):
    sku: str = Field(min_length=1, max_length=80)
    quantity: int = Field(gt=0, le=100)


class PlaceOrderRequest(BaseModel):
    customer_ref: str = Field(min_length=1, max_length=100)
    items: list[OrderItem] = Field(min_length=1)


def connect_database() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database() -> None:
    with closing(connect_database()) as connection:
        connection.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                customer_ref TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                idempotency_key TEXT UNIQUE,
                correlation_id TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS outbox (
                event_id TEXT PRIMARY KEY,
                order_id TEXT NOT NULL,
                event_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                published_at TEXT
            );
            """
        )
        connection.commit()


def create_order(
    request: PlaceOrderRequest, correlation_id: str, idempotency_key: str | None
) -> tuple[dict, bool]:
    now = datetime.now(timezone.utc).isoformat()
    order_id = str(uuid.uuid4())
    event_id = str(uuid.uuid4())
    event = {
        "event_id": event_id,
        "event_type": "OrderPlaced",
        "occurred_at": now,
        "correlation_id": correlation_id,
        "order_id": order_id,
        "customer_ref": request.customer_ref,
        "items": [{"sku": item.sku, "quantity": item.quantity} for item in request.items],
    }

    with closing(connect_database()) as connection:
        connection.execute("BEGIN IMMEDIATE")
        if idempotency_key:
            existing = connection.execute(
                "SELECT order_id, customer_ref, status, created_at, correlation_id "
                "FROM orders WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if existing:
                connection.rollback()
                return dict(existing), False

        connection.execute(
            "INSERT INTO orders"
            "(order_id, customer_ref, status, created_at, idempotency_key, correlation_id) "
            "VALUES (?, ?, 'ACCEPTED', ?, ?, ?)",
            (order_id, request.customer_ref, now, idempotency_key, correlation_id),
        )
        connection.execute(
            "INSERT INTO outbox(event_id, order_id, event_json, created_at) "
            "VALUES (?, ?, ?, ?)",
            (event_id, order_id, json.dumps(event), now),
        )
        connection.commit()

    return {
        "order_id": order_id,
        "customer_ref": request.customer_ref,
        "status": "ACCEPTED",
        "created_at": now,
        "correlation_id": correlation_id,
    }, True


def publish_pending_once() -> int:
    import pika

    with closing(connect_database()) as connection:
        rows = connection.execute(
            "SELECT event_id, event_json FROM outbox "
            "WHERE published_at IS NULL ORDER BY created_at LIMIT 50"
        ).fetchall()
    if not rows:
        return 0

    parameters = pika.URLParameters(AMQP_URL)
    parameters.heartbeat = 30
    connection = pika.BlockingConnection(parameters)
    try:
        channel = connection.channel()
        channel.queue_declare(queue=QUEUE_NAME, durable=True)
        channel.confirm_delivery()
        published_at = datetime.now(timezone.utc).isoformat()
        for row in rows:
            confirmed = channel.basic_publish(
                exchange="",
                routing_key=QUEUE_NAME,
                body=row["event_json"].encode("utf-8"),
                properties=pika.BasicProperties(
                    content_type="application/json",
                    delivery_mode=2,
                    message_id=row["event_id"],
                ),
                mandatory=True,
            )
            if confirmed:
                with closing(connect_database()) as database:
                    database.execute(
                        "UPDATE outbox SET published_at = ? "
                        "WHERE event_id = ? AND published_at IS NULL",
                        (published_at, row["event_id"]),
                    )
                    database.commit()
        return len(rows)
    finally:
        connection.close()


def outbox_worker() -> None:
    while True:
        try:
            publish_pending_once()
        except Exception as error:
            logger.error(
                json.dumps(
                    {
                        "service": "order",
                        "event": "outbox_publish_failed",
                        "error": str(error),
                    }
                )
            )
        time.sleep(POLL_INTERVAL)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    initialize_database()
    threading.Thread(target=outbox_worker, daemon=True, name="outbox-publisher").start()
    yield


app = FastAPI(title="MaltaShop Order Service", version="1.0.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    try:
        with closing(connect_database()) as connection:
            connection.execute("SELECT 1").fetchone()
    except sqlite3.Error as error:
        raise HTTPException(status_code=503, detail="database unavailable") from error
    return {"status": "ok", "service": "order"}


@app.post("/orders", status_code=201)
def place_order(
    payload: PlaceOrderRequest,
    x_correlation_id: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None),
) -> dict:
    correlation_id = x_correlation_id or str(uuid.uuid4())
    try:
        order, created = create_order(payload, correlation_id, idempotency_key)
    except sqlite3.IntegrityError as error:
        raise HTTPException(status_code=409, detail="idempotency key conflict") from error
    logger.info(
        json.dumps(
            {
                "service": "order",
                "event": "order_accepted" if created else "order_replayed",
                "order_id": order["order_id"],
                "correlation_id": order["correlation_id"],
            }
        )
    )
    return order
