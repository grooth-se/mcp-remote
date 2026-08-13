---
name: durabler2-development-status
description: Current state and architecture notes for the Durabler2 mechanical testing web app
metadata: 
  node_type: memory
  type: project
  originSessionId: a9cf2f8c-6df8-48b3-8ef6-eaa63c7a851c
---

# Durabler2 Development Status (2026-06-16)

## 2026-08-13 — Tensile report: removed hardcoded A5>18 / Z>40 requirement defaults (commit `19861ec41`, DEPLOYED + pushed)
- `utils/reporting/word_report.py` (~line 295): the tensile report injected `>18` for A5 and `>40` for Z when no requirement was supplied. Removed — A5/Z requirement cells now stay blank (`-`) unless supplied, matching Rm/Rp0.2 behaviour. Explicit requirements still pass through. `TensileReportGenerator` is the SOLE tensile report generator (used by app/tensile/routes.py + app/reports/routes.py); no duplicate. Deployed via utils/ rsync + rebuild; verified `>18`/`>40` gone in container.

## 2026-08-11b — Certificate register: Specimen SN column (commit `3d5a5e2ed`, DEPLOYED + pushed)
- Added "Specimen SN" column to certificates register list (`app/templates/certificates/index.html`), between Material and Tests, showing `cert.test_article_sn` (Certificate model field; `specimen_id` is a property alias). Template-only; search JS is column-index-independent, no colspan rows.
- Verified live on server (test-client GET `/certificates/` in container, HTTP 200): header order Certificate No.→Date→Test Order→Customer→Standard→Material→**Specimen SN**→Tests→Status→Approval→Actions; real SNs render (e.g. DUR-2026-1090→D106, 1088→D101-D104).

## 2026-08-11 — Tensile elastic-modulus fix: adjustable window + manual E override + R² (commit `23703474d`, DEPLOYED + pushed)
- Problem: extensometer noise at low load biased fitted Young's modulus HIGH (E 238–257 GPa vs physical ~200 for steel/weld metal on certs 1070–1073). E defines the Rp0.2/Rp0.5 offset lines. Verified via read-only diag on prod raw CSVs (RawTestData BLOB): elastic strains are tiny (~0.0004–0.0013 over 20–50% Rm window); apparent E per-point swings 48→886 GPa at low load; tangent-E by band shows the clean bands (R²>0.93) cluster at ~196–201 GPa.
- **COUNTERINTUITIVE (told user)**: widening the window DOWNWARD (to lower stress) makes E WORSE (266–294 GPa) because that's where the noise is. Moving window UP (30–60% Rm) → E 219–254, best R² (~0.98–0.99). Also: for these sharp-knee materials Rp0.2 is ~insensitive to E (<1 MPa across E 219→294); the visible problem is reported E itself.
- User decisions (AskUserQuestion): default window → **30–60% Rm**; manual control → **both window % AND explicit E override (GPa)**; R² → **analysis page only, NOT report**.
- Changes (6 files): `utils/models/test_result.py` MeasuredValue gains `r_squared: Optional[float]=None` (backwards-compat trailing field). `utils/analysis/tensile_calculations.py`: default `elastic_stress_fraction_range` (0.20,0.50)→**(0.30,0.60)**; `calculate_youngs_modulus` gains `slope_override_gpa` param (override slope, recompute R²/std_err vs windowed data) + sets `r_squared`. `app/tensile/forms.py`: 3 new fields `elastic_window_min`(30)/`elastic_window_max`(60)/`elastic_modulus_override`(GPa, blank=auto) + min<max validation in custom `validate()`. `app/tensile/routes.py`: read fields → config `elastic_stress_fraction_range=(min/100,max/100)` + pass override to normal-mode E call; store `geometry['elastic_window'|'elastic_modulus_override'|'elastic_r2']`; reanalyze GET now prefills these + uncertainty inputs (previously uncertainty inputs were NOT prefilled on reanalyze). `specimen.html`: new Elastic Modulus Evaluation card. `view.html`: R² colour-badge next to E (green≥0.99/amber≥0.97/red else) + "manual" badge, from `test.geometry.elastic_r2`.
- Prod recompute w/ new default (read-only, values NOT written): 1071 E 238.5→219.0 (R²0.988), 1072 257.2→253.9 (R²0.970), 1073 252.3→241.1 (R²0.982); Rp0.2 essentially unchanged. **Certs 1071/1072/1073 are PENDING_REVIEW (not published)** — operator will re-analyze via UI; I did NOT auto-re-analyze. Existing stored results are NOT auto-recomputed (same pattern as always).
- Verified: analyzer unit test (default window, window+E override, R²) + UI render/form-validation test ALL PASS local; live code + prod recompute confirmed. Scratchpad: test_modulus_unit.py, test_ui_render.py, verify_deploy.py, diag_modulus.py.

## 2026-07-08b — Statistics: dedup to latest record per specimen (commit `e3789e189`, DEPLOYED + pushed)
- Follow-up: chart still showed duplicate specimens (D28/D29/D30/D60). Cause: re-tested/modified specimens create NEW test records under the SAME published cert (new test_id, later created_at) instead of superseding via revision — so approved+latest-revision filters can't tell them apart. E.g. D28/cert1028: 4 records (ids 33,34,38,39).
- Fix: new `_latest_record_per_specimen_ids()` — `func.max(TestRecord.id)` grouped by (certificate_id, specimen_id, test_method) over the approved+latest-revision population; main query adds `.filter(TestRecord.id.in_(...))`. max(id)=newest (ids monotonic since 2026-05-13 CASCADE fix, no recycling). Applied to query + export.
- Prod verified: D28/D29/D30/D60 now appear once each (ids 39/45/42/60, the newest); TENSILE Rm rows 28→22. Local synthetic test extended with a 3x re-tested specimen → only newest kept. ALL PASS.

## 2026-07-08 — Statistics: approved-only latest report per cert + multi-material (commit `dcb061307`, DEPLOYED + pushed)
- `app/statistics/routes.py`: new `_approved_only(query)` joins `ReportApproval` on `certificate_id` and keeps `STATUS_APPROVED`/`STATUS_PUBLISHED` only. Applied to `query`, `export`, and the `index` material dropdown. Combined with existing `_latest_revision_filter()` → only the latest approved report per certificate number feeds statistics. Certificate join changed outer→inner (approved report always has a cert). Drafts/pending/rejected/revoked/no-cert excluded.
- Approval is **per-certificate** (ReportApproval.certificate_id, one-to-one). KEY: inclusion keys on the CERTIFICATE's approval, NOT the test-record's `.approval` backref. A published cert includes ALL its test records' AnalysisResults.
- Multi-material: `request.form.getlist('material')` + `TestRecord.material.in_(materials)` (was single `.get()` + ilike). Template `app/templates/statistics/index.html`: material text input → `<select multiple size=4>` (name still `material`). No JS change — FormData emits one entry per selected option; query fetch + export handler already iterate entries. JSON `filters.material`→`filters.materials`.
- Prod data (2026-07-08): 42 PUBLISHED approvals (0 APPROVED — signing auto-progresses), all with certificate_id. TENSILE 'n' returns 28 (approved-only 40 − 12 superseded revisions). Re-analyzed rec 31/32 (cert 1027 rev1, superseded) correctly EXCLUDED; rec 33/34/35 (certs 1028/1029 published, current rev) correctly INCLUDED.
- Verified: local synthetic test client (all cases: published/draft/pending/revoked, 2-revision cert, multi+single material, export) ALL PASS; prod read-only checks reconciled. Scratchpad scripts local_test_stats.py / diag_stats.py.
- GOTCHA: container Python 3.11 rejects backslash in f-string expressions (3.12 allows) — compute the substring outside the f-string in verify scripts.

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

## Index notes (moved from MEMORY.md 2026-07-14)
- **2026-07-08b Statistics dedup latest record per specimen (commit `e3789e189`, deployed + pushed)**: chart showed dup specimens (D28/D29/D30/D60) — re-tests create new records under same published cert. `_latest_record_per_specimen_ids()` keeps max(id) per (cert, specimen, method). Prod: TENSILE Rm 28→22 rows. Details in durabler2-status.md
- **2026-07-08 Statistics approved-only + multi-material (commit `dcb061307`, deployed + pushed)**: `_approved_only()` joins ReportApproval on certificate_id (APPROVED/PUBLISHED) + existing latest-revision filter → only latest approved report per cert number in statistics; material filter now multi-select (getlist + IN). Approval is per-CERTIFICATE not per-test-record. Details in durabler2-status.md
- **2026-07-06 Tensile records 31–35 RE-ANALYZED server-side (DONE)**: closed the pending June-12 task. Drove real `/tensile/specimen` route via test client, fed pristine CSV from RawTestData BLOB. rec31 Rp0.2 606.0/E 214.8 (was 124.9/98.4 garbage); rec33/34 Ag sign fixed −8.37→+8.37. GOTCHA: set `PORTAL_AUTH_ENABLED=false` before create_app or test-client bounces to `/`. DB backup `/data/durabler_pre_reanalyze_20260706.db`. Details in durabler2-status.md
- **2026-07-02 Upload 413 fix (durabler2 `6c6c5e8a5` + app_portal `ad0fa0e41`, deployed + pushed)**: 8 high-res images exceeded 50MB; raised Flask MAX_CONTENT_LENGTH (config.py) + nginx client_max_body_size (app_portal/nginx/nginx.conf, mounted volume→reload) to 100M. app_portal shares Durabler2's git remote. Details in durabler2-status.md
- **2026-07-02 Metallographic image limit 6→8 (commit `8f783fed9`, deployed + pushed)**: photo_7/photo_8 in forms.py, `range(1,9)` in routes.py + new.html; report/view iterate test.photos (no fixed limit). Details in durabler2-status.md
- **2026-06-25 Vickers adjustments (commit `658c796fa`, deployed + pushed)**: machine name → "QATM QNESS"; dwell default 10s; CSV first column = location; operator-selectable ASTM E140 HV→HBW column (non-austenitic steels, clamps out-of-range); units in readings header. New `utils/analysis/hardness_conversion.py`. NOTE: reports/routes.py is CRLF — don't flatten to LF. Details in durabler2-status.md
- **2026-06-23 Revoked status + latest-revision register (commit `cf9b41e78`, deployed + pushed)**: new REVOKED status (revision supersedes published → old revoked); report list shows latest revision only + defaults to hiding revoked; statistics use latest revision only; cert window gains Revision History panel. Details in durabler2-status.md
- **2026-06-16 Metallographic module (commit `0b4ddfb83`, DEPLOYED + pushed)**: 9th test type METALLO, ASTM E45/E381 + ISO 4967/4969, mirrors Charpy. Per-type inclusion severity A/B/C/D + acceptance limits → pass/fail, free-text macro, multiple captioned photos. Details in durabler2-status.md
- **subseavm01 disk gotcha (2026-06-16)**: `/` filled to 100% from accumulated Docker build cache; `docker builder prune -f` freed 55.9GB. Prune periodically.
- **2026-06-12b negative-strain-at-start fix (commit `67f6d9536`, deployed)**: `prepare_extensometer_strain()` zeroes at lowest reading + Annex G origin extrapolation; Ag/A% now from corrected strain
- **2026-06-12 tensile fixes (commit `43dd89fcb`, deployed 2026-06-12)**: extensometer sign now judged at max force (was last-sample → negated traces); elastic E window now 20-50% of max stress on loading branch (was absolute strain window → E=98.4/Rp0.2=124.9 garbage). Records 31-35 re-analyzed 2026-07-06 (DONE). Details in durabler2-status.md
- See [durabler2-status.md](durabler2-status.md) for full details
- Single portal-managed instance on SQLite, port 5002 (standalone retired 2026-05-12)
- Certificate approval workflow working for ALL 6 test types (TENSILE, CTOD, SONIC, FCGR, KIC, VICKERS) + Brinell + Charpy
- Currently in **user testing period** — waiting for feedback before resuming development
- Key file: `app/reports/routes.py` — contains all report generation helpers (~2800 lines)
- **2026-06-10 workflow audit fixes (commit `f137d47fd`, deployed; origin push pending)**: attachment-merge-before-sign, four-eyes guard, operator submit blocked, cert-delete orphan fix, /reports/help page — details in durabler2-status.md
- **Pending task**: [durabler2-nas-folder-task.md](durabler2-nas-folder-task.md) — auto-create cert folders on Synology NAS, blocked on SMB credentials
