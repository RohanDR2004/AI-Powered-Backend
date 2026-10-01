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

**Status: PENDING.** Redis was still finishing installation on this machine (a Windows UAC
prompt for the installer was awaiting manual approval) at the time this report was written. This
section will be filled in with the same command/parameters as Run 1 once Redis is confirmed
running, so the two runs are directly comparable. Expected (not yet measured) direction of
change, based on where each endpoint's time is currently going:
- `GET /tasks`: should drop further on cache hits (no Postgres round-trip for repeated reads).
- `POST /auth/register` / `POST /auth/login` / `POST /tasks`: should drop from ~0.9–2.8s down to
  roughly the real bcrypt/DB cost (tens of milliseconds), since the rate-limiter and Celery-enqueue
  timeouts stop being hit at all once Redis responds normally.

*(If you are reading this after that run was completed, check this file's git history / a later
commit for the filled-in numbers — this paragraph should have been replaced, not left standing
next to real data.)*

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
| Async I/O | Done | All 42 tests pass under async; live smoke tests in-session |
| Redis caching | Done, perf comparison pending | Code + unit tests done; Run 2 above pending Redis |
| Background processing (Celery) | Done | Unit test + live resilience test (bounded timeout) |
| DB indexes/pagination | Done | Matches actual query patterns; not independently benchmarked |
| Rate limiting | Done | Fail-open verified under both single-request and 20-user load tests |
| Docker | Done, run pending | See `docker-compose.yml`; actual `docker compose up` verification pending Docker Desktop install |
| Load testing | Done (baseline) | Run 1 above, 0% failures at 20 concurrent users |
