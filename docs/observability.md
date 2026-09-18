# Observability

This repository uses privacy-safe structured logs and Prometheus metrics for operational visibility.

## Local stack

Start the API and worker normally, then run:

```bash
cd observability
docker compose up -d
```

Prometheus is available on `http://localhost:9090` and Grafana on `http://localhost:3000`.

Set `GRAFANA_ADMIN_USER` and `GRAFANA_ADMIN_PASSWORD` in the environment before starting Grafana. Do not commit credentials.

## Correlation

The API accepts `X-Request-ID` and `X-Session-ID`. If no request ID is supplied, the API generates one and returns it in the response. Correlation values are carried in logging context and must be explicitly propagated when publishing Celery tasks.

## Privacy rules

Never log document text, prompts, model responses, access tokens, authorization headers, credentials, or raw PII. Prometheus labels must remain low-cardinality and must not contain IDs or user-controlled text.

## Alert semantics

The worker alerting rules focus on task-level failures. Queue depth/age and Celery heartbeat metrics are intentionally not collected from Redis because continuously polling the Celery broker adds unnecessary command traffic.

## Required worker integration

The worker process should expose the Prometheus registry on port `9100` and increment task counters from Celery task lifecycle signals. LLM, OCR, PII, HTOC, BM25, and task latency metrics remain available through the worker `/metrics` endpoint. The API metrics endpoint is exposed at `/metrics`.

The worker intentionally does not run a Redis-backed queue metrics polling loop or Celery heartbeat solely for observability. This keeps the observability layer from adding steady broker traffic when the worker is awake.
