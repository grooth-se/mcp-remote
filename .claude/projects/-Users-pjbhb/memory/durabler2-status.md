---
name: durabler2-development-status
description: Current state and architecture notes for the Durabler2 mechanical testing web app
metadata: 
  node_type: memory
  type: project
  originSessionId: a9cf2f8c-6df8-48b3-8ef6-eaa63c7a851c
---

# Durabler2 Development Status (2026-06-16)

## 2026-07-06 — Tensile records 31–35 RE-ANALYZED server-side (DONE; the long-pending June-12 task)
- Records 31–35 (TEN-20260612-001..005, specimens D27/D27/D28/D28/D29, certs DUR-2026-1027/1027/1028/1028/1029) were **status=ANALYZED, approval=None** (never published) — still held pre-fix values. Re-analyzed via a script driving the REAL `/tensile/specimen` route (test client) so fixed `mts_csv_parser` + `TensileAnalyzer` both ran.
- Method that worked: feed each record's **pristine original CSV from `RawTestData` BLOB** (`get_data()`, zlib) back to a temp file; set session `_user_id`(admin=1)/`tensile_csv_path`/`tensile_reanalyze_id`/`tensile_certificate_id`; rebuild SpecimenForm POST from record fields + geometry (reanalyze branch OVERWRITES specimen_id/material/batch/test_standard/temperature from the form — must feed them back or they wipe). `test_standard` must match SelectField choices (`ASTM E8/E8M-22`/`ISO 6892-1:2019`).
- **GOTCHA**: in the container `PORTAL_AUTH_ENABLED=true` installs a before_request that bounces test-client requests to `/` (302) before the route runs. Set `os.environ["PORTAL_AUTH_ENABLED"]="false"` BEFORE `from app import create_app`, and `WTF_CSRF_ENABLED=False`, so plain flask_login (`_user_id` session) satisfies `@login_required`.
- **GOTCHA**: reanalyze branch appends a NEW `raw_test_data` row without deleting the old → dedupe after (delete rows not in pre-run id set). Records 34 & 35 already had 2 csv raw rows pre-existing (harmless identical copies) — left as-is.
- Results (BEFORE→AFTER): **31 D27** Rp0.2 124.9→**606.0**, E 98.4→**214.8**, Ag 9.27→9.41 (the garbage-value fix). **33/34 D28** Ag **−8.37→+8.37** (parser sign fix). **32** (use_displacement_only) unchanged — correct, extensometer fix N/A. **35 D29** unchanged (already fixed-code output). All 5 have REANALYZE audit entries.
- DB backed up first at `/data/durabler_pre_reanalyze_20260706.db` (in durabler2 volume). No git change (data-only, in prod DB).

## 2026-07-02 — Upload limit 50MB→100MB (413 fix; durabler2 commit `6c6c5e8a5`, app_portal commit `ad0fa0e41`, DEPLOYED + pushed)
- Uploading 8 high-res micrographs hit HTTP 413. BOTH caps were 50MB: Flask `MAX_CONTENT_LENGTH` in `config.py` AND nginx `client_max_body_size` in `app_portal/nginx/nginx.conf` (server block, line ~22 — applies to all locations incl. durabler2). Raised both to 100M.
- nginx.conf is a **mounted volume** in `app_portal-nginx-1` (at `/etc/nginx/conf.d/default.conf`) — scp + `docker exec app_portal-nginx-1 nginx -s reload` applies it live, no rebuild. durabler2 bakes config.py via `COPY . .` so it needs a `--no-cache` rebuild.
- GOTCHA: app_portal repo shares the SAME git remote as Durabler2 (`grooth-se/mcp-remote.git`) — both push to that origin/main.
- Verified end-to-end through nginx on prod (curl multipart POST to `/app/durabler2/metallography/new`): 60MB → HTTP 302 (accepted, was 413 before), 110MB → HTTP 413 (new ceiling enforced). nginx checks body size before login_required, so probes work unauthenticated.

## 2026-07-02 — Metallographic image limit 6→8 (commit `8f783fed9`, DEPLOYED + pushed to origin)
- Raised max uploadable images in Metallographic module from 6 to 8. Three files, all under `app/`: `app/metallography/forms.py` (added photo_7/photo_8 + captions), `app/metallography/routes.py` (save loop `range(1, 7)`→`range(1, 9)`), `app/templates/metallography/new.html` (loop `range(1, 9)` + "up to 8 images" helper text). Report generator + view iterate over `test.photos` (no fixed limit), so no downstream change needed.
- Deployed: rsync `app/` → server, `docker compose build --no-cache durabler2` + up -d; verified photo_8/range(1,9)/"up to 8 images" live in container; route responds 302.

## 2026-06-25 — Vickers module adjustments (commit `658c796fa`, DEPLOYED + pushed to origin)
- Test machine name → **"QATM QNESS"** (was 'q-ness ATM test machine') in both report generators (`_generate_vickers_report` in reports/routes.py + standalone in vickers/routes.py)
- Standard dwell time default 15s → **10s** (forms.py + both report fallbacks)
- CSV import (`parse_vickers_csv`): **first column is now location** (was a running number); format `location;HV;method;d1;d2`. Single parse fn feeds both AJAX `/vickers/parse-csv` and server-side import.
- New operator-selectable `include_brinell` SelectField (default no) → adds **HBW column converted from HV per ASTM E140 Table 2 (non-austenitic steels)**. Header states standard; out-of-range HV **clamps to nearest tabulated value** (user choice). Conversion in `utils/analysis/hardness_conversion.py` (`vickers_to_brinell()` → (hbw, clamped)); table centralised + documented to verify vs controlled E140 copy.
- Units added to Individual Readings hardness header (HV load level) on screen + report
- `augment_readings_with_brinell()` + `BRINELL_COLUMN_HEADER` helpers in vickers/routes.py; reused by view + both report generators
- **GOTCHA**: `app/reports/routes.py` uses **CRLF line endings** — editing it with a Python `open().write()` flattens to LF and churns the whole file. Preserve CRLF (perl -pe 's/\n/\r\n/') when scripting edits to that file.
- Verified `/tmp/durabler2_verify/verify_vickers.py` (22 checks)

## 2026-06-23 — Revoked status + latest-revision report register (commit `cf9b41e78`, DEPLOYED + pushed to origin)
- New approval status `STATUS_REVOKED='REVOKED'` (dark badge) + `ReportApproval.revoke()` (keeps signed_pdf_path/pdf_hash)
- `create_revision` (certificates/routes.py): if superseded revision's approval is PUBLISHED → `.revoke()` + REVOKE audit entry. Delete guard now blocks PUBLISHED **and** REVOKED.
- Report list (`reports.index`): collapses each (year, cert_id) family to latest-revision approval (Python grouping post-query); status filter defaults to `'active'` (hides REVOKED); options `active`/`all`/individual statuses. Default arg changed from `''` to `'active'`.
- Statistics (`query`+`export`): `_latest_revision_filter()` helper (aliased Certificate subquery of superseded ids) excludes non-latest revisions; keeps NULL-cert rows. Only current revision data in analysis.
- Cert window: Revision History panel (all revisions of family w/ status badge + comment trace-back); view route passes `revisions`
- Verified `/tmp/durabler2_verify/verify_revoke.py` (12 checks). Pending: deploy + push.

## 2026-06-16 — Metallographic Examination module (commit `0b4ddfb83`, DEPLOYED + pushed to origin)
- New 9th test type: micro/macro eval of polished+etched surfaces, ASTM E45/E381 + ISO 4967/4969. Built to mirror Charpy module pattern.
- `test_method='METALLO'`, blueprint `metallography`, URL `/metallography`, test ID `MET-yymmdd-NNN`, color #6610f2, icon bi-zoom-in
- Data model (in TestRecord.geometry JSON): per-type inclusion severity A/B/C/D (0-5) + optional acceptance limits → auto pass/fail (`evaluate_inclusions` in app/metallography/routes.py); free-text micro_observations; free-text macro_evaluation; rating_method/magnification/micro_etchant/macro_etchant; multiple captioned photos (TestPhoto BLOBs, caption in .description). Severities also stored as AnalysisResult `Inclusion_A..D` so they show in cert review.
- Report generator `_generate_metallo_report` inline in app/reports/routes.py (like `_generate_charpy_report`); wired into cert-approval dispatch elif. CRUD mirrors Charpy: index/new/view/photo/report/delete (no edit/reanalyze, same as Charpy).
- Integrations: __init__.py register, navbar, dashboard card, cert Start-New button + test-list badge/view-button, cert standards dropdown (added E45/E381/ISO 4967/4969)
- Verified end-to-end: `/tmp/durabler2_verify/verify_metallo.py` (16 checks pass), ruff clean on new module
- User Q&A decisions: per-type severity (not full thin/heavy grid); macro free-text only (no S/R/C grid); multiple captioned photos; acceptance limits w/ pass/fail
- Deployed 2026-06-16: verified module files + `_generate_metallo_report` + blueprint live in `app_portal-durabler2-1`; route `/app/durabler2/metallography/` responds
- **Server disk gotcha (2026-06-16)**: `/` hit 100% during rebuild (repeated `--no-cache` builds piled up Docker build cache). Fixed with `docker builder prune -f` → freed 55.9GB (back to 41%). Run a `docker builder prune -f` periodically on subseavm01; build cache is the main culprit, not dangling images.

## 2026-06-12 — Tensile extensometer analysis fixes (commit `43dd89fcb`, DEPLOYED 2026-06-12)

## 2026-06-12b — Negative-strain-at-start correction (commit `67f6d9536`, DEPLOYED)
- User confirmed 1028 OK after first fix; 1027 had setup error (extensometer seating → negative strain at test start)
- New `TensileAnalyzer.prepare_extensometer_strain()`: zero at lowest reading on loading branch, then extrapolate elastic line (slope=E) to X/Y origin (Annex G); route uses it in normal mode; Ag + A% fallback now from corrected strain (not raw extension)
- 1027 verified: no negative strain on loading branch, Ag 9.41%, Rp0.2/Rp0.5 unchanged 606.0/636.6; Ag drift on old records ≤0.04%

## 2026-06-12 — Tensile extensometer analysis fixes (commit `43dd89fcb`, DEPLOYED 2026-06-12)
- Ref tests DUR-2026-1027 (rec 31) / DUR-2026-1028 (recs 33-35) exposed two bugs:
  1. `mts_csv_parser.py` flipped channel sign by last-vs-first sample; extensometer returns to ~0 after removal → whole positive trace negated (Ag=-8.37%, neg strain). Now judged at argmax(force).
  2. `_find_elastic_modulus_robust` selected elastic region by absolute strain window over full curve → seating offset put window on wrong segment (E=98.4, Rp0.2=124.9 on 1027); also reached past yield for low-Rp materials. Now stress window (config `elastic_stress_fraction_range`, default 20-50% of max stress) on loading branch only; legacy strain window as fallback.
- Regression vs all 20 tensile records in prod DB: certified values stable; fixed analyses give Rp0.2 606/607, E 215/231 GPa (consistent specimens D27/D28)
- Repro/regression scripts: `/tmp/durabler2_verify/{repro_tensile,regression_tensile}.py` (temp); prod DB copy at `/tmp/durabler2_verify/durabler_ref.db`
- **After deploy: records 31-35 must be RE-ANALYZED in the UI** (stored results not auto-recomputed); push to origin also pending

## Current State: Active User Testing
User testing in progress with real test data. Multiple improvements deployed.

## 2026-06-10 — Approval workflow audit + fixes (committed `f137d47fd`, DEPLOYED to server same day; push to origin pending — permission gate blocked direct push to main)
- Audited approval workflow end-to-end with a 26-check test-client script (kept at `/tmp/durabler2_verify/verify_workflow.py` — temp, recreate if needed)
- **Fixed**: PDF attachment now merged BEFORE X.509 signing (was merged after → invalidated signature; `append_pdf_attachment()` + `attachment_pdf` param in `utils/reporting/pdf_signer.py`); manual-upload approve no longer merges (warns instead — uploaded PDF must be complete)
- **Fixed**: four-eyes — submitter can no longer approve own report (`reports.approve` guard + review template hides button)
- **Fixed**: operators can no longer create/submit reports (`User.can_submit` excludes operator)
- **Fixed**: cert delete now blocked if report PUBLISHED; otherwise deletes approval row (was orphaning it via FK nullify)
- **Fixed**: submit checks Word file exists on disk; /reports/ Test Method filter implemented (was a dead dropdown); reports index shows methods/specimen for cert-based approvals
- **Added**: help page `/reports/help` (workflow guide, roles, FAQ) + navbar Help link + contextual links on certificate view & review page
- **Known gaps reported, not fixed**: no CSRF protection on any POST form (app-wide change), open redirect in login `next` param, no automated test suite in repo

## Deployment Topology
- **Single portal-managed instance**: `app_portal-durabler2-1` (SQLite at `/data/durabler.db`)
- Standalone stack retired 2026-05-12 — was empty (1 admin user, 0 tests); volumes preserved
- Port mapping `5002:5005` on the portal docker-compose `durabler2` service so port 5002 reaches the portal-managed instance (in addition to nginx route `/app/durabler2/`)
- Intent was Postgres; staying on SQLite because that's where the real data is

## 2026-05-13 — Charpy photo orphan fix (committed + pushed)
- **Symptom**: regenerated Charpy report for cert DUR-2026-1008 embedded an old PQR/CTOD photo on top of the actual Charpy photo
- **Root cause**: SQLite recycled test_record id=25 after a previous record was deleted. Five child tables (`test_photos`, `raw_test_data`, `analysis_results`, `report_files`, `report_approvals`) had FK to `test_records` with `ON DELETE NO ACTION` and `PRAGMA foreign_keys=OFF`, so deleting a parent left orphan children that "inherited" by the new record with the recycled id.
- **Data fix**: deleted photo id=5 (recycled-id case) + 18 FK-violation orphans (5 photos + 13 raw_test_data). Binaries backed up to `/data/orphan_backups/` on the durabler2 container volume. Pre-rebuild DB snapshot at `/data/orphan_backups/durabler_pre_cascade_*.db`.
- **Schema fix**: rebuilt all 5 child tables with `ON DELETE CASCADE` on the FK to `test_records` (commit `226619bf0`).
- **Code fix**: `app/extensions.py` registers an SQLAlchemy `Engine.connect` listener that runs `PRAGMA foreign_keys=ON` per SQLite connection. Models updated in `app/models/test_data.py`, `test_record.py`, `report_approval.py`.
- **Report regenerated**: DUR-2026-1008 Charpy report regenerated at `reports/drafts/DUR-2026-1008_20260513_155858.docx` (122 KB, 1 fracture photo embedded — bytes match photo id=15 `Slagprovserie D11 brottyta.jpg`).
- All three Durabler2-related commits pushed to `origin/main`: `226619bf0` (CASCADE), `442ddeca1` (port 5002 mapping), `8eaa3ed5b` (subcalc service registration).

## What's Working
- Full certificate approval workflow for all 6 test types: TENSILE, CTOD, SONIC, FCGR, KIC, VICKERS
- Workflow: Analyze → Generate Report → redirects to Certificate page → Submit → Review → Approve & Sign → Download PDF
- Automatic PDF signing pipeline: stamp approval in Word → LibreOffice convert → X.509 crypto signature
- Manual PDF upload fallback if LibreOffice/certificate unavailable
- Photos from DB (TestPhoto BLOB) included in reports for CTOD, FCGR, KIC, Vickers
- Statistics page with query, chart, and CSV export (fixed join + property issues)
- Portal auth syncs display_name on every login (used for test engineer + PDF signature)
- Reverse proxy prefix handled via ScriptNameMiddleware in portal_auth.py
- Vickers CSV import from q-ness test machine (semicolon, Swedish decimals, LINE structure)
- Vickers PDF attachment merged into final signed report (pypdf merge after signing)
- Tensile report chart uses stored plot_data from analysis (exact match with browser chart)
- Break point detection: stress threshold + strain reversal + sudden stress drop
- Uncertainty inputs connected to all analyzers (calibrated defaults: force 0.31%, displacement 0.16%)
- ISO 17025 uncertainty budget report in docs/uncertainty_budget_report.md

## Deployment
- **Production**: app_portal docker-compose manages durabler2 container
- Deploy: `rsync ... && ssh ... "cd app_portal && docker compose build --no-cache durabler2 && docker compose up -d durabler2"`
- **IMPORTANT**: Use `--no-cache` on docker build — cached layers may serve stale code even after rsync
- **IMPORTANT**: After rsync, verify with `docker compose exec -T durabler2 grep ...` that new code is in container
- Do NOT use standalone `Durabler2/docker-compose.yml` — causes duplicate container
- Gunicorn on port 5005 inside container, nginx proxies `/app/durabler2/` to it

## Key Architecture Notes
- `Certificate.certificate_number` is a **Python @property** (not a DB column) — use `Certificate.year` + `Certificate.cert_id` in SQL queries
- `TestRecord.results` is a **relationship** to `AnalysisResult`
- `TestRecord.geometry` is a **JSON column** — stores specimen dimensions, raw data, photos paths, plot_data, pdf_attachment
- `TestRecord.photos` is a **relationship** to `TestPhoto` — BLOB storage
- `ReportFile` with `report_type='pdf_attachment'` stores Vickers PDF attachments (compressed BLOB)
- `ReportApproval` linked to Certificate via `certificate_id`; states: DRAFT → PENDING_REVIEW → APPROVED → PUBLISHED
- Report Word docs saved to `reports/drafts/`, signed PDFs to `reports/signed/{year}/`
- Approval table: 2-column format (Role / Name+Signature), 1.5cm row heights
- Tensile plot_data stored in geometry during analysis for report chart consistency
- Vickers CSV parser: `parse_vickers_csv()` in `app/vickers/routes.py`

## Recent Changes (2026-03-19 to 2026-04-10)
- Redirect to certificate page after report generation (all 6 modules)
- Include DB photos in test reports (CTOD, FCGR, KIC, Vickers)
- Use full_name (display name) for test engineer in all reports
- Populate sign page with test record and approver details
- Sync display name from portal on every login
- Fix double WSGI middleware (proxy prefix)
- Fix statistics: use DB columns not property, explicit join path
- Remove numeric values from chart legends in report plots
- Connect form uncertainty inputs to all analyzers
- Update defaults: force 0.31%, displacement 0.16%
- Fix displacement strain zeroing (subtract initial position)
- Enable Sonic Resonance in navbar dropdown
- Allow approvers to import certificates from Excel
- Rename "Extensometer Length" → "Gage Length (extensometer)", A% → A5
- Fix ReH/ReL yield method in tensile reports (rate data lookup)
- Break detection: 3 methods (stress threshold + strain reversal + sudden drop)
- Store truncated plot_data during analysis for report chart
- Fix CTOD report: missing fields, CTOD value display, decimal formatting
- Add missing certificate fields to all report templates
- Vickers CSV import from q-ness machine + PDF attachment upload
- Merge PDF attachment into signed Vickers report
