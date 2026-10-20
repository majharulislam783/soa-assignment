import json
import logging
import os
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timezone

import pika


DATABASE_PATH = os.getenv("NOTIFICATION_DB_PATH", "notifications.db")
AMQP_URL = os.getenv("AMQP_URL", "amqp://guest:guest@localhost:5672/%2F")
QUEUE_NAME = "order.placed"
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(message)s")
logger = logging.getLogger("notification-service")


def connect_database() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database() -> None:
    with closing(connect_database()) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS notification_jobs (
                event_id TEXT PRIMARY KEY,
                order_id TEXT NOT NULL,
                correlation_id TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.commit()


def process_event(body: bytes) -> dict:
    event = json.loads(body)
    required = {
        "event_id",
        "event_type",
        "order_id",
        "correlation_id",
        "occurred_at",
    }
    if not required.issubset(event) or event["event_type"] != "OrderPlaced":
        raise ValueError("invalid OrderPlaced event")

    with closing(connect_database()) as connection:
        cursor = connection.execute(
            "INSERT OR IGNORE INTO notification_jobs"
            "(event_id, order_id, correlation_id, status, created_at) "
            "VALUES (?, ?, ?, 'QUEUED', ?)",
            (
                event["event_id"],
                event["order_id"],
                event["correlation_id"],
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        connection.commit()
        inserted = cursor.rowcount == 1
    logger.info(
        json.dumps(
            {
                "service": "notification",
                "event": "notification_queued" if inserted else "duplicate_ignored",
                "event_id": event["event_id"],
                "order_id": event["order_id"],
                "correlation_id": event["correlation_id"],
            }
        )
    )
    return {"inserted": inserted, "event": event}


def on_message(channel, method, properties, body: bytes) -> None:
    try:
        process_event(body)
    except (ValueError, json.JSONDecodeError):
        logger.exception(
            json.dumps(
                {
                    "service": "notification",
                    "event": "invalid_message",
                    "message_id": properties.message_id,
                }
            )
        )
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    except sqlite3.Error:
        logger.exception("notification persistence failed")
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
    else:
        channel.basic_ack(delivery_tag=method.delivery_tag)


def consume_forever() -> None:
    while True:
        connection = None
        try:
            parameters = pika.URLParameters(AMQP_URL)
            parameters.heartbeat = 30
            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()
            channel.queue_declare(queue=QUEUE_NAME, durable=True)
            channel.basic_qos(prefetch_count=20)
            channel.basic_consume(queue=QUEUE_NAME, on_message_callback=on_message)
            logger.info(
                json.dumps(
                    {
                        "service": "notification",
                        "event": "consumer_ready",
                        "queue": QUEUE_NAME,
                    }
                )
            )
            channel.start_consuming()
        except pika.exceptions.AMQPError:
            logger.exception("message broker connection failed; retrying")
            time.sleep(3)
        finally:
            if connection is not None and connection.is_open:
                connection.close()


if __name__ == "__main__":
    initialize_database()
    consume_forever()
