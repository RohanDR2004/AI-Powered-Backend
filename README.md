# AI-Powered Applications Backend Platform

A FastAPI backend providing JWT authentication, task CRUD, AI text generation (OpenAI), and
per-user activity logging, backed by PostgreSQL — built in two phases:

- **Phase 1**: core backend (auth, CRUD, AI integration, validation, docs, tests).
- **Phase 2**: scalability, performance, and production-readiness (async I/O, Redis caching,
  Celery background processing, DB optimization, rate limiting, security hardening, Docker,
  cloud deployment config, monitoring, load testing).

## Architecture

```
app/
  main.py                 FastAPI app, lifespan (DB init), middleware, exception handlers,
                           /health and /metrics
  config.py                Settings loaded from environment variables (.env)
  database.py               Async SQLAlchemy engine/session (asyncpg) — used by the API
  database_sync.py          Sync SQLAlchemy engine/session (psycopg2) — used by Celery workers
  redis_client.py           Shared async Redis client (caching, rate limiting, health check)
  cache.py                  Bounded, fail-safe cache get/set/invalidate helpers
  rate_limit.py             Async, Redis-backed fixed-window rate limiter (FastAPI dependency)
  celery_app.py              Celery application (Redis broker/backend)
  models/                   SQLAlchemy ORM models (User, Task, ActivityLog)
  schemas/                  Pydantic request/response schemas
  auth/                     Password hashing, JWT creation/validation, auth dependency
  routers/                  API route handlers (auth, users, tasks, ai, activity_logs)
  services/                 AI provider integration (async OpenAI client)
  workers/                  Celery tasks (activity logging)
tests/                      Pytest test suite (Phase 1 + Phase 2)
locustfile.py                Load test definitions
Dockerfile, docker-compose.yml   Containerization (api, worker, db, redis)
render.yaml                 Render deployment blueprint
requirements.txt
.env.example
```

Two database engines exist on purpose: the FastAPI app talks to Postgres asynchronously
(`asyncpg`, via `app/database.py`) so a slow query doesn't block other requests on the same
process, while Celery workers run as plain synchronous processes and use a regular `psycopg2`
session (`app/database_sync.py`) against the same database — there's no benefit to forcing an
event loop into a worker process that just runs one task at a time.

## Phase 1 Functionality

- `POST /auth/register`, `POST /auth/login` — registration + JWT login, bcrypt password hashing,
  duplicate-email rejection
- `GET /users/me` — current authenticated user
- `POST/GET/GET-by-id/PUT/DELETE /tasks` — CRUD, scoped to the authenticated user
- `POST /ai/generate` — OpenAI-backed text generation; returns `503` with a clear message if
  `OPENAI_API_KEY` isn't set, instead of crashing
- `GET /activity-logs` — per-user activity history (login, task changes, AI requests)
- Request validation via Pydantic, proper HTTP status codes, Swagger (`/docs`) + ReDoc (`/redoc`)
- Postman collection, pytest test suite

## Phase 2 Improvements

| Area | What changed | Why |
|---|---|---|
| **Async I/O** | Full migration to async SQLAlchemy (`asyncpg`); all routes are `async def`; bcrypt hashing runs in a thread (`asyncio.to_thread`) so it can't block the event loop; AI calls use `AsyncOpenAI` | A slow DB query, password hash, or AI response no longer ties up the whole process the way a sync stack would |
| **Redis caching** | `GET /tasks` and `GET /tasks/{id}` are cached (TTL `CACHE_TTL_SECONDS`), invalidated on create/update/delete | Avoids re-querying Postgres for data that didn't change between requests |
| **Background processing** | Activity logging moved to a Celery task (`app/workers/tasks.py`), broker/backend = Redis | It's called from every action but the client never needs to wait for it, and Celery gives retry-on-failure for free |
| **DB optimization** | Index on `tasks.owner_id`; composite index on `activity_logs(user_id, created_at)`; pagination (`skip`/`limit`) on list endpoints; tuned connection pool (`DB_POOL_SIZE`/`DB_MAX_OVERFLOW`) | Indexes match the actual query patterns (ownership filter, per-user history sorted by date); pagination bounds response size as data grows |
| **Rate limiting** | Custom async, Redis-backed limiter on `/auth/register`, `/auth/login`, `/ai/generate` | Protects the cheapest-to-abuse, most expensive endpoints; see **Why not slowapi** below |
| **Security** | CORS via `ALLOWED_ORIGINS`; generic 500 handler (no stack traces leaked); `/docs` togglable via `ENABLE_DOCS`; startup warning if `JWT_SECRET_KEY` is left at its default | Reduces what an attacker can learn from a misbehaving endpoint |
| **Docker** | `Dockerfile` + `docker-compose.yml` (api, worker, db, redis) | One-command local stack |
| **Deployment** | `render.yaml` blueprint (web service, worker, managed Postgres, managed Redis) | Deployment config prepared without touching any account |
| **Monitoring** | Request-timing middleware + logging; `GET /health` (checks DB and Redis independently); `GET /metrics` (Prometheus format) | Visibility into latency and dependency health |
| **Load testing** | `locustfile.py` | Real, measured numbers instead of guesses — see `PERFORMANCE_REPORT.md` |

### Why not slowapi (rate limiting)?

The obvious choice for FastAPI rate limiting is the `slowapi` library. Reading its source
(`slowapi/extension.py`) showed that even for `async def` routes, it checks the Redis-backed
counter **synchronously, inline, with no offloading** — the exact pattern that was found (and
fixed) for Celery's `.delay()` in this project: a blocking network call made directly inside an
`async def` function freezes the *entire* event loop, not just the one request, for as long as
that call takes. Against an unreachable Redis, this was observed to block for 60+ seconds. Rather
than build on a library with that failure mode, `app/rate_limit.py` is a small dependency on top
of the app's own async Redis client, with every call bounded by `asyncio.wait_for` and designed
to fail open (allow the request) if Redis is slow or down. This was verified live: with Redis
unreachable, login/register/task endpoints all kept working with bounded latency instead of
hanging or taking the server down for other clients.

## Setup (local, no Docker)

### 1. Create a virtual environment and install dependencies

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

### 2. PostgreSQL

Install PostgreSQL and create the databases:

```sql
CREATE DATABASE ai_backend;
CREATE DATABASE ai_backend_test;   -- used by pytest
```

### 3. Redis

Install Redis (or run `docker run -p 6379:6379 redis:7-alpine` if you'd rather not install it
natively) and make sure it's reachable at the URL in `REDIS_URL`. The app **runs without Redis**
— caching, rate limiting, and background activity logging all degrade gracefully (see the Phase 2
table above) — but Docker/Celery/rate-limit behavior is best verified with it running.

### 4. Configure environment variables

```bash
cp .env.example .env
```

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string (async driver, e.g. `postgresql+asyncpg://...`) |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | Async connection pool sizing |
| `JWT_SECRET_KEY` | Secret used to sign JWT access tokens — **change this in production** |
| `JWT_ALGORITHM` | JWT signing algorithm (default `HS256`) |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | Access token lifetime in minutes |
| `OPENAI_API_KEY` | OpenAI API key, required for `/ai/generate` (optional at startup) |
| `OPENAI_MODEL` | OpenAI chat model name (default `gpt-4o-mini`) |
| `REDIS_URL` | Redis connection string (caching, rate limiting, Celery broker/backend) |
| `CACHE_TTL_SECONDS` | How long cached task data is kept (default 30s) |
| `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | Override Celery's broker/backend; default to `REDIS_URL` |
| `CELERY_TASK_ALWAYS_EAGER` | `true` runs Celery tasks inline (used automatically by the test suite) |
| `RATE_LIMIT_LOGIN` / `RATE_LIMIT_REGISTER` / `RATE_LIMIT_AI_GENERATE` | e.g. `5/minute` |
| `ENVIRONMENT` | Free-text label (`development`/`production`) |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins |
| `ENABLE_DOCS` | `false` disables `/docs`, `/redoc`, `/openapi.json`, and `/metrics` from the schema |

### 5. Run the application

```bash
uvicorn app.main:app --reload
```

- API root: http://127.0.0.1:8000/
- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc
- Health check: http://127.0.0.1:8000/health
- Metrics: http://127.0.0.1:8000/metrics

Database tables are created automatically on startup.

### 6. Run the Celery worker (optional, for background activity logging)

```bash
celery -A app.celery_app worker --loglevel=info --pool=solo
```

`--pool=solo` is required on Windows (the default `prefork` pool needs `fork`, which Windows
doesn't have). On Linux/macOS (including inside the Docker container) the default pool works
fine and `--pool=solo` can be omitted. Without a worker running, activity logging simply doesn't
get written (the enqueue call fails open after a bounded wait) — everything else keeps working.

## Running with Docker

```bash
docker compose up --build
```

This starts Postgres, Redis, the API (`http://localhost:8000`), and a Celery worker, all wired
together on Docker's own network. Set `JWT_SECRET_KEY` and `OPENAI_API_KEY` in your shell (or a
`.env` file next to `docker-compose.yml` — compose reads it automatically for `${VAR}`
substitution) before running; no secrets are baked into the image or the compose file.

## Deployment (Render)

`render.yaml` is a [Render Blueprint](https://render.com/docs/blueprint-spec) defining the web
service, a Celery worker, a managed Postgres database, and a managed Redis instance. **No account
action has been taken** — this is configuration only. To actually deploy:

1. Push this repository to GitHub (already done for this project).
2. In the Render dashboard: **New +** → **Blueprint**, select this repo. Render reads
   `render.yaml` and provisions the services.
3. The blueprint marks `JWT_SECRET_KEY`, `OPENAI_API_KEY`, and `ALLOWED_ORIGINS` as
   `sync: false` — Render will prompt you to fill these in manually (they're secrets/environment-
   specific and deliberately not in the file). Set a long random value for `JWT_SECRET_KEY`, your
   real key for `OPENAI_API_KEY`, and your deployed frontend's origin for `ALLOWED_ORIGINS`.
4. Render builds and starts the web service and worker; `DATABASE_URL` and `REDIS_URL` are wired
   automatically from the managed Postgres/Redis instances it creates.

## API Documentation

Swagger UI (`/docs`) and ReDoc (`/redoc`) are generated from the code and always up to date.
Authenticate in Swagger via **Authorize** → paste the JWT from `/auth/login` (no `Bearer` prefix
needed, Swagger adds it).

## Testing

```bash
pytest -v
```

Tests run against `ai_backend_test` (async SQLAlchemy, tables dropped/recreated per test) and set
`CELERY_TASK_ALWAYS_EAGER=true` automatically, so Celery tasks run inline without needing a real
worker or broker. Coverage includes Phase 1 (auth, CRUD, JWT protection, validation) and Phase 2
(pagination, caching hit/invalidation, rate-limit allow/deny/fail-open, the Celery task itself,
the bounded-timeout resilience fix, `/health`, `/metrics`, CORS, config URL normalization).

## Load Testing (Locust)

```bash
locust -f locustfile.py --host http://127.0.0.1:8000
```

Opens a web UI at http://localhost:8089 to configure users/spawn-rate interactively. For a
scripted/headless run:

```bash
locust -f locustfile.py --host http://127.0.0.1:8000 \
    --headless -u 20 -r 5 -t 30s --csv=performance_reports/perf_run
```

Simulated users register, log in, then repeatedly hit the health check, list tasks, and create
tasks — never use real credentials or a production host. See `PERFORMANCE_REPORT.md` for actual
measured results.

## Performance Testing

See [`PERFORMANCE_REPORT.md`](PERFORMANCE_REPORT.md) for the methodology, environment, and
measured before/after numbers (caching, rate limiting, and background processing all change
latency under load — the report shows what was actually measured, not estimated).

## Postman

Import `postman_collection.json` into Postman. Set the collection variable `base_url`
(default `http://127.0.0.1:8000`) and `access_token` after logging in.

## Security Notes

- Passwords are hashed with bcrypt, never stored in plain text.
- JWT secret, DB credentials, and API keys are read from environment variables, never hard-coded;
  a startup check warns (server-side log only) if `JWT_SECRET_KEY` is left at its insecure default.
- `.env` is excluded from version control via `.gitignore`; `.env.example` documents every
  variable without real values.
- CORS is restricted to `ALLOWED_ORIGINS` rather than left open.
- Unhandled exceptions return a generic `500` to the client; the real error (with traceback) is
  logged server-side only.
- `/docs`, `/redoc`, `/openapi.json`, and `/metrics` can be disabled via `ENABLE_DOCS=false`.
- All database access goes through the SQLAlchemy ORM (parameterized queries) — no raw SQL,
  so no SQL-injection surface.
- Rate limiting protects `/auth/register`, `/auth/login`, and `/ai/generate` from abuse.
