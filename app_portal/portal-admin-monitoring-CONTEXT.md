# CLAUDE.md — App Portal: Admin Monitoring & Usage Analytics Extension

> **Project:** Extension to the existing Subseatec App Portal (`app_portal`)
> **Target host:** `172.27.55.104` — HPE ProLiant ML110 Gen11, 64 GB RAM, Ubuntu Server, Docker Compose + nginx
> **Owner:** Peter (Managing Director, Subseatec S AB)
> **Status:** Context/spec — written against the actual codebase, ready for Claude Code
> **Delivery model:** Incremental, phased, review gate after every phase.

---

## 0. Read this first — what already exists

This file is written **against the real `app_portal` source**, not assumptions. The extension must **build on** the existing structure, reuse existing helpers, and follow existing conventions. Do not introduce new patterns where one already exists.

Confirmed facts about the current codebase (do not re-verify from scratch, but read the files before editing them):

- **Stack:** Flask 3.1, **Flask-SQLAlchemy 3.1.1** (classic `db.Model` / `db.Column` style — *not* typed SQLAlchemy 2.0 `Mapped[...]`), Flask-Login, Flask-WTF (CSRF on, API blueprint exempted), PyJWT. **Served by gunicorn with `--workers 2`** (see `docker-entrypoint.sh`).
- **DB:** SQLite at `/data/portal.db` (`SQLALCHEMY_DATABASE_URI` in `app/config.py`). `TestingConfig` uses in-memory SQLite.
- **App factory:** `create_app(config_class=Config)` in `app/__init__.py`; blueprints registered there; `db.create_all()` runs at startup.
- **Migrations:** *No Alembic.* Schema upgrades are done with **idempotent `ALTER TABLE` blocks in `docker-entrypoint.sh`** plus `db.create_all()` for new tables. Follow this exact pattern — new tables need nothing (create_all handles them); new columns on existing tables need a guarded ALTER in the entrypoint.
- **RBAC already exists:** `app/utils/decorators.py` → `@admin_required` (login_required + `current_user.is_admin`, else `abort(403)`). `User.is_admin` boolean already on the model. **Reuse this; do not build new RBAC.**
- **Admin system blueprint already exists:** `admin_system_bp` registered at `/admin/system` (`app/routes/admin/system.py`), already serving `/sessions`, `/access-log`, `/audit-log`. **The new monitoring routes go here.**
- **Logging infrastructure already exists:** `app/models/log.py` → `AccessLog` (user_id, app_id, action ∈ {login, logout, access_app, denied}, ip_address, timestamp, details) and `AuditLog`. Helpers in `app/utils/logging.py` → `log_access(...)`, `log_audit(...)`. **Reuse these.**
- **Health service exists:** `app/services/app_health.py` → `check_health(url)`, `check_all_apps()`.
- **Frontend:** server-rendered Jinja + **Bootstrap 5** (dark navbar, `bi-` icons, dropdowns) + `app/static/js/portal.js`. **No HTMX, no Plotly, no build step.** The admin nav dropdown in `templates/base.html` is gated by `{% if current_user.is_admin %}`.
- **Tests:** pytest with fixtures in `tests/conftest.py` (`admin_user`, `normal_user`, `logged_in_client`, `user_logged_in_client`, `sample_app(s)`). Login endpoint is `POST /login`.

### Critical architecture note (affects Feature 3)
nginx proxies `/app/<code>/` **directly to each app container** — the portal is **not** in the request path for in-app activity. Therefore the portal **cannot** see per-request activity inside apps via a Flask `before_request` hook. The portal's real visibility into app usage is:
1. `AccessLog` events it already writes (`login`, `logout`, `access_app` on launch, `denied`), and
2. calls each app makes to `POST /api/validate-token` when establishing a session.

Feature 3 is built from these portal-side signals (see §5). True request-level in-app logging would require nginx-log ingestion or each app self-reporting — treated as an **optional** deeper phase, not the default.

**When the code and this file disagree, the code wins — flag it and ask.**

---

## 1. Goal

Add an **admin-only** monitoring area under `/admin/system` providing:

1. **Live server/infrastructure status** — host CPU, memory, disk, load, uptime (of the 64 GB Ubuntu host) plus per-container Docker stats.
2. **Historical workload** — the above sampled on a schedule, stored, and charted over selectable ranges.
3. **Per-app usage analytics** — extended, queryable usage per app and per user, built from `AccessLog` (who used what, how often, last used), with filtering and CSV export.

All routes reuse `@admin_required`. Non-admins must not see the nav entries or reach the routes (403).

---

## 2. Scope

### In scope
- New routes on the **existing** `admin_system_bp` (`/admin/system/...`).
- New models `MetricSample`, `MetricHourly` (classic `db.Model` style, in a new `app/models/metrics.py`).
- Host + container metrics service; live dashboard with lightweight polling of a JSON endpoint (vanilla `fetch`, matching `portal.js` — **not** HTMX).
- Scheduled sampling + retention/roll-up via a **separate collector process/service** (see §4.1 — required because gunicorn runs 2 workers).
- Historical charts using **Chart.js via CDN** (matches the portal's CDN/Bootstrap, no-build approach). Plotly is an acceptable alternative only if Peter prefers it — flag the choice, don't assume.
- Per-app usage analytics over `AccessLog` + CSV export.
- New nav entries in the admin dropdown in `templates/base.html`.
- Tests in `tests/test_monitoring.py`.

### Out of scope (state, do not build)
- Alerting/notifications — note as future only.
- Any change to auth, `@admin_required`, or the token flow.
- Editing users/apps/permissions from these views (observe only).
- Prometheus/public metrics endpoints.
- Cross-host aggregation.

---

## 3. Feature 1 — Server / infrastructure status

### 3.1 Host metrics (`psutil`)
Collect: CPU % overall + per-core, load average (1/5/15), memory (total/used/available/%), swap, disk usage per mount, disk I/O, network I/O, boot time / uptime, process count.

**Container-visibility caveat:** the portal runs inside a container, so `psutil` sees the container, not the 64 GB host. Resolve via the **collector service** in §4.1, which is given read-only host mounts (`/proc`, `/sys`, and `/:/host:ro`) and points psutil at them. Keep the host mounts on the collector, **not** on the web-facing portal container.

### 3.2 Container metrics (Docker)
Per container: name, image, status, health, restart count, CPU %, memory usage/limit, net + block I/O.

**Security — do not mount the raw Docker socket read-write into the portal.** Add a `docker-socket-proxy` (e.g. `tecnativa/docker-socket-proxy`) service to the Compose stack exposing **read-only** endpoints (`CONTAINERS=1`, all else `0`), reachable only on the internal Compose network. Query it over HTTP. Prefer `urllib`/`http.client` (already used in `app_health.py`) to avoid adding the `docker` SDK dependency. Record this decision in the PR; note the residual risk if a plain read-only socket mount is used instead.

### 3.3 Live dashboard
- Route: `GET /admin/system/status` → `templates/admin/system/status.html` (extends `admin/layout.html`).
- Data route: `GET /admin/system/status/data` → JSON (host + containers). `@admin_required` on both.
- Refresh: small vanilla-JS poller in a new `app/static/js/admin_monitor.js` calling the data route every N seconds (default 5, configurable), updating cards/tables. Match `portal.js` style; keep CSRF-safe (GET only).

---

## 4. Feature 2 — Historical workload

### 4.1 Collector (must not run per-worker)
gunicorn runs **2 workers**, so an in-process `APScheduler` would double-sample. Use a **dedicated collector** instead:
- **Preferred:** a separate `collector` service in `docker-compose.yml` built from the **same image**, run with a different command that executes a sampling loop (or a cron/systemd timer calling a Flask CLI command). This service carries the read-only host mounts (§3.1) and talks to the socket proxy — isolating privileged access from the portal.
- Expose the sampler as a Flask CLI command: `flask collect-metrics` (one sample) and `flask rollup-metrics` / `flask purge-logs` for maintenance. Register CLI in `create_app` or a small `app/cli.py`.
- Default sample interval 60 s (env-configurable). If Peter prefers a single container, an alternative is an inter-process lock so only one gunicorn worker samples — document whichever is chosen.

### 4.2 Storage & retention — `app/models/metrics.py`
Classic Flask-SQLAlchemy style (match `app/models/log.py`), UTC timestamps via `lambda: datetime.now(timezone.utc)`:

```python
class MetricSample(db.Model):
    __tablename__ = 'metric_sample'
    id = db.Column(db.Integer, primary_key=True)
    ts = db.Column(db.DateTime, index=True, default=lambda: datetime.now(timezone.utc))
    scope = db.Column(db.String(64), index=True)   # 'host' or container name
    cpu_pct = db.Column(db.Float)
    mem_used = db.Column(db.BigInteger)             # bytes
    mem_total = db.Column(db.BigInteger)
    disk_json = db.Column(db.Text)                  # per-mount usage as JSON
    extra_json = db.Column(db.Text)                 # loadavg/net/io as JSON

class MetricHourly(db.Model):
    __tablename__ = 'metric_hourly'
    id = db.Column(db.Integer, primary_key=True)
    hour = db.Column(db.DateTime, index=True)
    scope = db.Column(db.String(64), index=True)
    metric = db.Column(db.String(32), index=True)  # 'cpu_pct','mem_pct',...
    v_min = db.Column(db.Float); v_avg = db.Column(db.Float); v_max = db.Column(db.Float)
```
Register both in the `create_app` import list so `db.create_all()` builds them (no ALTER needed — brand-new tables). Retention: keep raw N days (default 7), roll up to hourly kept M days (default 90), delete beyond. Both configurable in `app/config.py`.

### 4.3 Charts
- Route `GET /admin/system/workload` → `templates/admin/system/workload.html`.
- Data route `GET /admin/system/workload/data?range=24h&scope=host&metric=cpu_pct` → JSON series (reads raw for short ranges, `metric_hourly` for long). Ranges: 1h / 24h / 7d / 30d / custom.
- Render with Chart.js (CDN) line charts: CPU %, memory %, disk % per mount, top-N containers by CPU/memory.

---

## 5. Feature 3 — Per-app usage analytics (built on `AccessLog`)

### 5.1 Data source
Use the existing `AccessLog` (do not add a new logging table unless needed). First **ensure the signals are complete**: confirm `access_app` is logged on launch in `dashboard`/`auth`, and add a `log_access(..., action='validate')` (or reuse `access_app`) inside `POST /api/validate-token` in `app/routes/api.py` so app-session establishment is captured with `app_id`, `user_id`, `ip_address`, `timestamp`. Never log tokens or secrets in `details`.

### 5.2 Analytics service — `app/services/usage_analytics.py`
Aggregate `AccessLog` into: per-app usage counts over a date range, per-user-per-app counts, last-used timestamp per app, unique users per app, denied-access counts. Use SQLAlchemy `func.count` / `group_by`; index `AccessLog.timestamp`, `action` (add indexes via the entrypoint ALTER pattern if missing).

### 5.3 Views
- `GET /admin/system/usage` → `templates/admin/system/usage.html`: filters (app, user, date range, action), summary table + a Chart.js bar chart of usage per app.
- `GET /admin/system/usage/data` → JSON for the chart/table (server-side pagination like the existing `access_log` route: `paginate(page=..., per_page=50)`).
- `GET /admin/system/usage/export.csv` → streamed CSV of the current filtered set (use a generator + `Response(..., mimetype='text/csv')`; do not build the whole file in memory).

### 5.4 Optional deeper phase (only if requested)
Request-level in-app logging via nginx access-log ingestion (parse `/app/<code>/...` lines, attribute by path/user) **or** apps POSTing usage events to a portal ingest endpoint. Note as future; do not build by default.

---

## 6. Access control & nav
- Every new route uses `@admin_required` (already returns 403 for non-admins). Add a test asserting 403 for `user_logged_in_client` on each new route.
- Add nav entries in the admin dropdown in `templates/base.html` (inside the existing `{% if current_user.is_admin %}` block): "Server Status" → `admin_system.status`, "Workload History" → `admin_system.workload`, "App Usage" → `admin_system.usage`. Use `bi-` icons consistent with the existing menu.

---

## 7. Security & compliance
- **Docker socket:** read-only socket proxy only (§3.2). Biggest risk in this work — treat seriously.
- **Host mounts:** read-only, on the collector service only, never the portal.
- **GDPR:** `AccessLog` links identifiable users to activity = personal data. Define a retention period (default 90 days, configurable), document purpose (operational/security monitoring), restrict to admins (already enforced), and provide `flask purge-logs --days N`. Flag for the Subseatec GDPR register. Same retention discipline applies to `metric_sample`.
- **No secrets in logs / no tokens in `details`.**
- Size-limit CSV export to avoid an accidental multi-million-row synchronous dump.

---

## 8. Dependencies
Add to `requirements.txt` (pin consistently with the existing pinned style): **`psutil`** only, ideally. Avoid adding the `docker` SDK (use `urllib`/`http.client` against the socket proxy). Avoid `APScheduler` if the collector uses a cron/systemd timer or loop; add it only if an in-process scheduler is chosen. Chart.js is loaded via CDN in the template — no Python dependency.

Compose additions: `docker-socket-proxy` service (read-only); `collector` service (same image, sampler command, read-only host mounts). Portal container stays unprivileged and unchanged except for new routes/templates/static.

---

## 9. Implementation phases (review gate after each — stop and wait)

**Phase 0 — Scaffold & confirm.** Read the files named in §0. Add the three new routes to `admin_system_bp` as stubs returning placeholder pages, add nav entries, add `tests/test_monitoring.py` asserting 403 for non-admins and 200 for admins on all three. Confirm the open questions in §11. **Gate.**

**Phase 1 — Live server status.** `system_metrics` service (host via psutil, containers via socket proxy), `/status` + `/status/data`, `admin_monitor.js` poller, `status.html`. Read-only, no persistence. **Gate.**

**Phase 2 — Collector + storage.** `app/models/metrics.py`, `flask collect-metrics` / `rollup-metrics` / `purge-logs` CLI, `collector` service in compose with host mounts, retention/roll-up. Verify only one sampler runs. **Gate.**

**Phase 3 — Workload history.** `/workload` + `/workload/data`, Chart.js time-series reading raw + hourly. **Gate.**

**Phase 4 — Per-app usage analytics.** Ensure `AccessLog` signals complete (incl. validate-token logging), `usage_analytics` service, `/usage` + `/usage/data` + `/usage/export.csv`, `usage.html`. **Gate.**

**Phase 5 — Hardening.** Socket proxy locked read-only, GDPR purge wired + documented, indexes added via entrypoint pattern, test coverage, update `portal-context.md`. **Gate.**

> Deliver each phase as a self-contained change with its own summary. Do not batch phases. Wait for review at each gate.

---

## 10. Conventions (match the existing portal exactly)
- Classic Flask-SQLAlchemy models (`db.Model`, `db.Column`), UTC timestamps via `datetime.now(timezone.utc)`.
- Blueprint routes on `admin_system_bp`; templates under `templates/admin/system/` extending `admin/layout.html`.
- Bootstrap 5 markup, `bi-` icons; new JS in `app/static/js/admin_monitor.js` following `portal.js`.
- Schema changes via `docker-entrypoint.sh` idempotent ALTER + `db.create_all()` — **no Alembic**.
- pytest with existing conftest fixtures; add to `tests/`. Login is `POST /login`.
- Keep new logic in `app/services/` (`system_metrics.py`, `metrics_collector.py`, `usage_analytics.py`); keep routes thin.

---

## 11. Open questions for Peter (answer at Phase 0)
1. **Charts:** Chart.js via CDN (recommended, matches the no-build portal) or Plotly (your usual house style)?
2. **Collector:** dedicated `collector` service (recommended) vs cron/systemd timer vs in-process lock in one gunicorn worker?
3. **Docker container stats:** OK to add a `docker-socket-proxy` service to the stack?
4. **Retention defaults:** raw metrics 7 d / hourly 90 d / access logs 90 d — acceptable?
5. **Deeper per-app logging:** is portal-side usage analytics (§5.1–5.3) enough for now, or do you want nginx-log ingestion (§5.4) in scope?
6. **Live-view interval:** default 5 s polling OK, or slower to keep load trivial?
