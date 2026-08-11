# Project Memory

## Server & Deployment
- [Server deployment](server-deployment.md) — `ssh administrator@172.27.55.104` (subseavm01); no git on server, deploy via rsync/scp + docker compose rebuild; nginx 8080/8443, apps at `https://<ip>:8443/app/<name>/`
- [Deployment separation](feedback_familjekontor_standalone.md) — Familjekontor standalone on Mac Mini; server apps (heatsim, app_portal, Durabler2, …) via Docker on subseavm01
- [Mac Mini](mac-mini-deployment.md) — `peterjansson@192.168.50.134`, no git, deploy via scp
- subseavm01 gotcha: Docker build cache fills `/` — run `docker builder prune -f` periodically (freed 55.9GB 2026-06-16)

## App Portal (2026-07-14)
- [app-portal-status.md](app-portal-status.md) — central auth gateway at `/Users/pjbhb/app_portal`, **112 tests**; local `python run.py` port 5050 (`BEHIND_PROXY=false`); server: compose, all apps ONLINE
- **2026-07-15 admin monitoring extension DEPLOYED (commit `216add9b2`, local only — push blocked: remote is PUBLIC, holds memory+code)**: /admin/system/status|workload|usage, collector + socket-proxy services live, collector sampling 16 containers
- SSO cookie fix deployed 2026-06-09: distinct `SESSION_COOKIE_NAME` per app/portal

## Durabler2 (2026-08-11)
- [durabler2-status.md](durabler2-status.md) — material test cert app, portal-managed SQLite, port 5002; in **user testing period**; fixes deployed+pushed (2026-08-11 tensile elastic-modulus: adjustable 30–60%Rm window + manual E override + R² display, commit `23703474d`; statistics dedup + approved-only, tensile 31-35 re-analysis, 100MB uploads, metallo module, Vickers, revoked-status register)
- Key file `app/reports/routes.py` (~2800 lines); reports/routes.py is CRLF — don't flatten to LF
- Pending: [durabler2-nas-folder-task.md](durabler2-nas-folder-task.md) — NAS cert folders, blocked on SMB credentials

## Familjekontor
- [familjekontor-status.md](familjekontor-status.md) — architecture, Phases 1-7 details, all patterns/lessons (moved from this index 2026-07-14)
- Flask accounting app, port 5004, 34 blueprints, **1218 tests**; git root is `/Users/pjbhb` (not the app dir); Swedish labels
- [familjekontor-toolchain.md](familjekontor-toolchain.md) — TRB-style toolchain, ruff baseline `a85d262f8`

## Bäverligan OOM (2026-06-29)
- [baverligan-status.md](baverligan-status.md) — golf-league OOM app at `/Users/pjbhb/Beaver` (own repo), port 5012, **50 tests**; M1-M3 + league rules + Windows PyInstaller packaging done
- Remaining: build/test .exe ON Windows (no cross-compile); confirm prize categories with league

## SubseaCalc (2026-06-09)
- [subcalc-status.md](subcalc-status.md) + [subcalc-architecture-decisions.md](subcalc-architecture-decisions.md) — Flask at `/Users/pjbhb/subcalc` (own repo), port 5009, **372 tests**
- DEPLOYED at `/app/subcalc/`; Phase 2 complete (import, browse, exporters, material, cost, quote, designer, sync bridge)
- Phase 3 candidates: validation vs legacy oracle, WPQR module

## TRB (2026-05-21)
- [trb-status.md](trb-status.md) — Flask at `/Users/pjbhb/TRB` (own repo), port 5008, deployed; reads Durabler2 DB read-only; [feedback_trb_kept_files.md](feedback_trb_kept_files.md): keep root `.docx` + `trb-context-doc-2.md` tracked
- Next: bulk generation paused; email distribution + per-customer templates queued

## Heatsim (2026-06-10)
- [heatsim-status.md](heatsim-status.md) — Flask, port 5004 local, dual DB, **683 tests**; deployed (`app_portal-heatsim-1`, portal `/app/heatsim/`)
- 2026-06-10 deployed: materials curve editor, interactive Plotly plots, bug sweep

## MPQP Generator (2026-03-10)
- [mpqp-generator-status.md](mpqp-generator-status.md) — Flask at `/Users/pjbhb/mpqp-generator`, port 5003, 108 tests; deployed standalone (PORTAL_AUTH_ENABLED=false), Ollama on host
- Next: run full scan + indexing for historical projects

## SAAMsim (2026-03-05)
- [saamsim-status.md](saamsim-status.md) — own repo at `/Users/pjbhb/SAAMsim`, port 5005, **299 tests**, 11 blueprints
- 8-week MVP: chemistry/TTT-CCT/geometry/thermal/phase done → validation → WPQR → deploy

## Accrued Income (2026-03-05)
- [accruedincome-status.md](accruedincome-status.md) — Flask at `/Users/pjbhb/accruedincome`, Phases 1-2 complete, Phase 3 (AI) not started
- Delete-closing-date feature deployed but not committed; user pending: run 2026-02-28 calculation

## MG5integration (2026-02-27)
- [mg5integration-status.md](mg5integration-status.md) — Monitor G5 ERP → SQLite → REST API for Accrued Income & SPInventory; 14 tables, 68 tests; in **user testing period**

## HTtracker (2026-05-19)
- [httracker-status.md](httracker-status.md) — external dev's Flask app adapted for portal, deployed (`/app/heattreattracker/`, own repo); fresh DB on server, awaiting user end-to-end test

## Docsorter (2026-05-08) — COMPLETE
- [docsorter-status.md](docsorter-status.md) — PDF archive sorter on Mac Mini; ~29.7k PDFs filed to `/Volumes/RED2TB/Sorterade/`, 39 unclassifiable remain

## pitfurnacecogne (2026-07-10)
- [pitfurnacecogne-status.md](pitfurnacecogne-status.md) — pit furnace reheat planner (Cogne), own repo, port 5010; M0-M3 + Windows packaging done (53 tests), gateways G0-G3 awaiting review
- ALL remaining work needs Peter/Cogne input (gateway reviews, §9 data, Windows build)
