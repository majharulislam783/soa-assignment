# MaltaShop SOA / Microservices Assignment

**Student:** Majharul Islam (11718)
**Institution:** Learnkey Institute, Malta
**Assessment:** Unit 5 — Service-Oriented Architecture and Microservices Fundamentals
**Submission date:** 22 October 2026

This repository contains the report source (`report.md`), the formatted submission (`report.pdf`) and a small place-order prototype under `prototype/`.

## Prototype

The Order service owns an SQLite order database and transactional outbox. It exposes `POST /orders`, commits the order and event intent together, then publishes asynchronously to a durable RabbitMQ queue. The Notification service consumes the event, writes its own notification job and acknowledges only after persistence. Both services log the same correlation ID. Notification deduplicates by `event_id`, while the Order API supports a client-supplied `Idempotency-Key`.

From this directory, with Docker Engine and the Compose plugin installed:

```powershell
cd prototype
docker compose up --build
```

In another terminal, submit a test order and inspect the consumer log:

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://localhost:8000/orders `
  -Headers @{'X-Correlation-ID'='demo-corr-001'; 'Idempotency-Key'='demo-request-001'} `
  -ContentType 'application/json' `
  -Body '{"customer_ref":"customer-demo","items":[{"sku":"lamp-1","quantity":1}]}'
docker compose logs notification
```

Swagger UI is at `http://localhost:8000/docs`; RabbitMQ management is at `http://localhost:15672`. The Compose password is for local demonstration only and must be replaced using a secrets manager before any shared or deployed use.

### Environment variables

| Variable | Service | Purpose | Default |
|---|---|---|---|
| `ORDER_DB_PATH` | Order | SQLite file path | `orders.db` |
| `NOTIFICATION_DB_PATH` | Notification | SQLite file path | `notifications.db` |
| `AMQP_URL` | Both | RabbitMQ connection URL | local broker URL |
| `OUTBOX_POLL_INTERVAL` | Order | Outbox polling interval in seconds | `1` |
| `RABBITMQ_USER` | Compose | Local broker username | `malta` |
| `RABBITMQ_PASSWORD` | Compose | Local broker password | `local-only-change-me` |
| `LOG_LEVEL` | Both | Python log level | `INFO` |

## Tests and evidence

The unit tests cover atomic order/outbox persistence, request idempotency, event validation, consumer deduplication and correlation-ID propagation. GitHub Actions runs these tests, starts the full Compose stack, sends a real order request, checks that Notification consumes the event with the same correlation ID, publishes the actual response/logs to the workflow summary, and uploads them as a run artifact. The passing run and its actual response/log evidence are also included under `evidence/`.

To run the unit tests locally:

```powershell
python -m pip install -r prototype/order_service/requirements.txt `
  -r prototype/notification_service/requirements.txt pytest
python -m pytest prototype/order_service/test_app.py `
  prototype/notification_service/test_consumer.py -q
```

Generate or refresh the PDF after editing the Markdown source with:

```powershell
python render_report.py
```
