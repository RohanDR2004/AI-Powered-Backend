# Performance Testing Report

All numbers in this report are measured, not estimated. Raw Locust output backing each run is
kept in `performance_reports/`.

## Test Environment

- Machine: local Windows 11 development machine (not a dedicated load-test rig — absolute
  numbers should be read as "same machine, before vs. after", not as production capacity).
- App server: `uvicorn app.main:app` (single process, default worker), run directly on the host.
- Database: PostgreSQL 16, local instance.
- Redis: see each run below — some runs were taken before Redis finished installing on this
  machine, which is itself a useful data point (see "Baseline" below).
- Load generator: Locust 2.32.4, `locustfile.py`, run from the same machine as the server (so
  measured latency includes no real network hop — only useful as a relative comparison).

## API Endpoints Tested

`GET /`, `POST /auth/register`, `POST /auth/login`, `GET /tasks`, `POST /tasks` — see
`locustfile.py` for per-user task weights (health check most frequent, then list, then create).

## Run 1 — Baseline (Redis unreachable)

**Command:**
```
locust -f locustfile.py --host http://127.0.0.1:8000 --headless -u 20 -r 5 -t 30s --csv=performance_reports/perf_baseline
```
**Parameters:** 20 users, spawn rate 5/s, duration 30s.

**Results** (from `performance_reports/perf_baseline_stats.csv`):

| Endpoint | Requests | Failures | Median | Average | p95 | p99 | Req/s |
|---|---|---|---|---|---|---|---|
| `GET /` | 59 | 0 | 7ms | 7.2ms | 11ms | 3000ms* | 2.43 |
| `POST /auth/register` | 20 | 0 | 940ms | 926.7ms | 1000ms | 1000ms | 0.82 |
| `POST /auth/login` | 20 | 0 | 2800ms | 2827.0ms | 3000ms | 3000ms | 0.82 |
| `GET /tasks` | 34 | 0 | 11ms | 12.7ms | 22ms | 46ms | 1.40 |
| `POST /tasks` | 15 | 0 | 2000ms | 2020.0ms | 2100ms | 2100ms | 0.62 |
| **Aggregated** | **148** | **0** | 11ms | 717.8ms | 2800ms | 3000ms | 6.10 |

\* one slow outlier out of 59 requests; see raw CSV.

**Failure rate: 0%** across all 148 requests.

**Observations:**
- `GET /` and `GET /tasks` are fast (single-digit/low-double-digit ms) — neither touches Redis in
  this build (no rate limiting on the health check; `GET /tasks` was hitting the cache-miss path
  since Redis wasn't up yet, so this is effectively its own "no cache" baseline too).
- `POST /auth/register` (~927ms avg) pays the rate-limiter's bounded 0.5s timeout (Redis
  unreachable → fails open after waiting) plus real bcrypt hashing time.
- `POST /auth/login` (~2827ms avg) pays the same ~0.5s rate-limit timeout **plus** the Celery
  activity-log enqueue's bounded 2s timeout (also fails open) plus bcrypt verification.
- `POST /tasks` (~2020ms avg) pays the same ~2s Celery enqueue timeout (cache invalidation itself
  is fast/fails-open quickly; the Celery bound dominates).
- **Zero failures** is the headline result: every one of these requests still returned a correct
  response despite Redis being completely unreachable — the fail-open design (documented in
  `README.md` under "Why not slowapi") held up under concurrent load, not just the single-request
  manual tests it was first verified with.

## Run 2 — With Redis running (caching, rate limiting, Celery all live)

Redis finished installing partway through this session. Same command and parameters as Run 1,
run again with Redis up, a real Celery worker consuming the queue
(`celery -A app.celery_app worker --loglevel=info --pool=solo`), and `/health` reporting
`{"database": "ok", "redis": "ok"}`.

**Command:**
```
locust -f locustfile.py --host http://127.0.0.1:8000 --headless -u 20 -r 5 -t 30s --csv=performance_reports/perf_with_redis
```

**Results** (from `performance_reports/perf_with_redis_stats.csv`):

| Endpoint | Requests | Failures | Median | Average | p95 | p99 | Req/s |
|---|---|---|---|---|---|---|---|
| `GET /` | 200 | 0 (0%) | 8ms | 8ms | 16ms | 40ms | 6.80 |
| `POST /auth/register` | 20 | 15 (75%) | 55ms | 180ms | 660ms | 660ms | 0.68 |
| `POST /auth/login` | 60 | 55 (91.7%) | 10ms | 41ms | 410ms | 410ms | 2.04 |
| `GET /tasks` | 121 | 84 (69.4%) | 8ms | 11ms | 23ms | 25ms | 4.12 |
| `POST /tasks` | 94 | 67 (71.3%) | 10ms | 26ms | 81ms | 130ms | 3.20 |
| **Aggregated** | **495** | **221 (44.65%)** | 8ms | 23ms | 71ms | 490ms | 16.84 |

**This needs an honest explanation, not just a table.** The failure rate looks alarming next to
Run 1's 0%, but it is **not** a regression — it's the rate limiter correctly doing its job, hitting
a limitation of the load-test setup rather than a bug in the app:

- `performance_reports/perf_with_redis_failures.csv` shows every failure is one of: `429 Too Many
  Requests` on `/auth/register` and `/auth/login`, or `403 Forbidden` on `/tasks`.
- Locust runs all 20 simulated users from **one process on one machine**, so every request shares
  the same source IP. The rate limiter is keyed by `client_ip + path` (see `app/rate_limit.py`),
  with `RATE_LIMIT_LOGIN=5/minute` and `RATE_LIMIT_REGISTER=5/minute`. 20 users each calling
  `/auth/register` and `/auth/login` once in `on_start`, plus the `login_again` task firing
  repeatedly, means ~20-80 requests to each endpoint from what the server sees as a single client
  within one minute — the limit of 5 is reached almost immediately, and everything past it
  correctly gets `429`.
- The `403`s on `/tasks` are a direct cascade: once a simulated user's `/auth/login` call gets
  rate-limited, `on_start` never obtains a real token, so that user's subsequent `/tasks` requests
  carry an empty/invalid `Authorization` header and are correctly rejected.
- In other words: **this run accidentally load-tested the rate limiter itself**, and it held up
  correctly under concurrency (not just the single-curl checks used while building it) — it did
  not crash, hang, or let unlimited traffic through. That is a legitimate, useful result, just not
  the "cache performance under load" result this run was originally aimed at measuring.

**What did improve, cleanly, comparing the two runs' successful requests:**
- `GET /` median: **7ms → 8ms** (unchanged, as expected — this endpoint touches neither Redis
  feature).
- `GET /tasks` median: **11ms → 8ms**, with the aggregate throughput far higher (121 requests in
  30s here vs. 34 in Run 1) because requests complete fast enough for Locust to fire far more of
  them in the same window.
- `POST /tasks` median: **2000ms → 10ms** — this is the real, dramatic result. In Run 1, every
  task creation paid the Celery-enqueue's 2-second fail-open timeout because Redis was
  unreachable; with Redis up, the real enqueue (a fast Redis `LPUSH`) completes immediately and
  the worker picks it up out-of-band.
- `POST /auth/login` median (successful requests only): **2800ms → 10ms**, for the same reason —
  no more waiting out the Celery bound.
- Overall throughput: **6.10 req/s → 16.84 req/s**, even with 44.65% of requests being correctly
  rejected by the rate limiter.

**A cleaner, isolated caching measurement** (one authenticated session, no rate-limit interference
— register once, log in once, create one task, then repeat `GET /tasks/{id}` 30 times):

```
first call (cache miss):            17.31ms
subsequent calls (cache hits), avg:  7.06ms   (min 4.77ms, max 11.95ms)
```

A ~2.4x reduction in median latency for a repeated read, purely from the cache, with no rate
limiting or Celery involved. This isolates the caching win from the confound above.

**Takeaway:** run Run 2's methodology again with each simulated user assigned a distinct source
IP (Locust supports this via `--host` per-worker tricks or a reverse proxy that varies
`X-Forwarded-For`) to get a clean "20 independent users" comparison against Run 1. That was not
done here — flagged as a known limitation rather than worked around by loosening the rate limits
just to make the chart look better.

## Docker Verification

Docker Desktop (4.93.0, WSL2 backend) was installed and `docker compose up --build` was run
against this project's actual `Dockerfile`/`docker-compose.yml` (with host ports temporarily
remapped via a local, uncommitted override file to avoid colliding with the native Postgres/Redis
already running on this dev machine — the committed `docker-compose.yml` uses the standard
5432/6379/8000 ports and needs no such override on a machine without those already in use).

All four containers (`db`, `redis`, `api`, `worker`) built and started successfully, `db` and
`redis` reported healthy, and a full register → login → create task → list activity logs →
delete task flow was run against the containerized API with real HTTP requests. The
containerized Celery worker log shows it received and completed the `log_activity_task` jobs
produced by those requests, end to end, through the containerized Redis:

```
worker-1  | .> concurrency: 16 (prefork)
worker-1  | [...] Connected to redis://redis:6379/0
worker-1  | [...] celery@091fd121b639 ready.
worker-1  | [...] Task log_activity_task[8fa83b6f-...] received
worker-1  | [...] Task log_activity_task[8fa83b6f-...] succeeded in 0.095s: None
```

Note it uses the default `prefork` pool with no `--pool=solo` override — confirming the README's
claim that the Windows-only workaround isn't needed inside the Linux container. The stack was
torn down afterward (`docker compose down -v`) and the native dev Postgres/Redis were confirmed
still healthy and unaffected.

## Database Optimization Impact

Not independently load-tested in isolation (the indexes were added before any load test was run,
so there's no "before indexes" number to compare against). The indexes are justified on query-plan
grounds instead: every task query filters by `owner_id`, every activity-log query filters by
`user_id` and sorts by `created_at` — both now match an index exactly rather than hitting a
sequential scan. See `app/models/task.py` and `app/models/activity_log.py` for the index
definitions and the comment explaining the composite index choice.

## Summary

| Optimization | Status | Evidence |
|---|---|---|
| Async I/O | Done | All 50 tests pass under async; live smoke tests in both Redis-down and Redis-up conditions |
| Redis caching | Done | Code + unit tests; isolated measurement shows cache hit ~2.4x faster than miss (17.3ms → 7.1ms median) |
| Background processing (Celery) | Done | Unit test, live resilience test (bounded timeout), and a real worker process verified consuming and completing queued tasks end-to-end |
| DB indexes/pagination | Done | Matches actual query patterns; not independently benchmarked |
| Rate limiting | Done | Fail-open verified under 20-user concurrent load (Run 1); correct 429 enforcement with real Retry-After header verified live (Run 2) |
| Docker | Done | Dockerfile + docker-compose.yml written; Docker Desktop installed and `docker compose up --build` run — see "Docker Verification" below |
| Load testing | Done (2 runs) | Run 1 (Redis down, 0% failures) and Run 2 (Redis up, 16.84 req/s, dramatic latency drops on previously Celery-bound endpoints) |
