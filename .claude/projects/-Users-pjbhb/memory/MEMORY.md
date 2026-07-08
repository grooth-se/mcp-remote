# Project Memory

## Bäverligan OOM Status (2026-06-23) — M1-M3 + league rule fixes
- See [baverligan-status.md](baverligan-status.md)
- Golf-league Order of Merit app (Degerfors Golf), Flask + SQLite, port 5012, own git repo at `/Users/pjbhb/Beaver`
- M1 (`1d3172a`) scoring+models+standings; M2 (`8de2659`) docx import; M3 (`c3822ee`) exports + lock/recompute + finale
- 2026-06-23 (`a43f928`): **Snitt = round(mean of 5 best/lowest scores)** CONFIRMED (derived, not manual); **OOM total = best 15 rounds** (season up to ~20); **import matches name-first, Golf-ID second** + refreshes Golf-ID (no more dup members). Merged 6 round-11 dup members via scripts/fix_round11_duplicates.py
- Live dev DB seeded from workbook: **59 members, 11 rounds, 330 results**, 46 real Golf-IDs + 13 TMP
- 2026-06-29 (`09fe6ca`): **Windows standalone packaging** — PyInstaller (`BaverliganOOM.spec`, --onefile/console) + **waitress** WSGI + `run_app.py` entry (free port, opens browser, Swedish msg). `app/paths.py`: DB at `<Documents>/Bäverligan OOM/baverligan.db` via platformdirs (OneDrive-aware), created first-run only (never overwrites); `resource_path()` uses sys._MEIPASS when frozen. `create_app(db_path=, template_folder=, static_folder=)`. BUILD.md has the build cmd. **.exe MUST be built ON Windows** (no cross-compile). Print view = A4 landscape, font auto-scales to round count. **50 tests, ruff clean**
- Remaining: build/test .exe on a Windows PC; confirm prize categories w/ league
- Note: weasyprint can't load on this Mac (missing native libs) — PDF is browser print-to-PDF

## Deployment Separation
- See [feedback_familjekontor_standalone.md](feedback_familjekontor_standalone.md)
- **Familjekontor**: standalone on Mac Mini at home, NOT on the Linux server
- **Server apps** (heatsim, app_portal, Durabler2, etc.): deployed on Linux server via Docker

## Mac Mini (Home)
- See [mac-mini-deployment.md](mac-mini-deployment.md)
- `peterjansson@192.168.50.134`, familjekontor at `~/familjekontor`, no git, deploy via scp

## Docsorter Status (2026-05-08) — COMPLETE
- See [docsorter-status.md](docsorter-status.md) for full details
- PDF archive sorter at `/Users/pjbhb/Docsorter`, runs on Mac Mini (`~/Docsorter`)
- All 4 phases done: main run + re-OCR + large files + duplicate merge
- ~29,700 PDFs → ~29,353 documents filed in `/Volumes/RED2TB/Sorterade/<Issuer>/`
- Local Ollama `gemma3:4b`, tesseract OCR, batch classify (5 pages/call)
- 4,250 issuer folders, 39 unclassifiable files remain

## Server & Deployment
- See [server-deployment.md](server-deployment.md) for full details
- Production server: `ssh administrator@172.27.55.104` (hostname: subseavm01)
- No git on server — deploy via rsync/scp + docker compose rebuild
- Nginx on ports 8080/8443, apps at `https://<ip>:8443/app/<appname>/`
- Nginx proxy buffers: 256k for general (server block), 1MB for heatsim (location block)

## MPQP Generator Status (2026-03-10)
- See [mpqp-generator-status.md](mpqp-generator-status.md) for full details
- Flask app at `/Users/pjbhb/mpqp-generator`, port **5003**, 108 tests
- All 7 phases complete, deployed on server at `172.27.55.104:5003`
- Portal auth disabled (standalone mode), Ollama on host, CIFS mount for historical projects
- Background scan with progress bar, PDF timeout protection (30s SIGALRM)
- **Next**: run full scan + indexing for historical projects

## App Portal Status (2026-04-10)
- See [app-portal-status.md](app-portal-status.md) for full details
- Central auth gateway at `/Users/pjbhb/app_portal`, **77 tests passing**
- Local dev: `python run.py` on port **5050**, `BEHIND_PROXY=false`
- Server: Docker compose, `BEHIND_PROXY=true`, all 8 apps ONLINE (heattreattracker deployed 2026-05-19)
- MPQP Generator running with PORTAL_AUTH_ENABLED=false (standalone on port 5003)
- Session lifetime 24h (deployed 2026-04-13)
- heattreattracker compose service committed 2026-06-10 (`83331b3dc`)
- **SSO session-cookie fix DEPLOYED 2026-06-09**: distinct `SESSION_COOKIE_NAME` per app/portal so launching one app no longer logs you out of others (details in app-portal-status.md)

## SAAMsim Status (2026-03-05)
- See [saamsim-status.md](saamsim-status.md) for full details
- Own git repo at `/Users/pjbhb/SAAMsim`, port **5005**
- Weeks 1-5 + post-W5 COMPLETE: **299 tests passing**, 11 blueprints, 19 models
- **Latest**: Wire/flux on BuildConfiguration, chemistry-driven phase prediction (weld metal dilution), simulation edit/reconfigure route
- Key services: `app/services/chemistry/`, `app/services/ttt_cct/`, `app/services/geometry/`, `app/services/thermal/`, `app/services/phase/`
- Navbar: Dashboard | Materials | Chemistry | TTT/CCT | Consumables | Processes | Builds | Geometry | Thermal
- 8-week MVP: ~~chemistry~~ ~~TTT/CCT~~ ~~geometry~~ ~~thermal~~ ~~phase~~ → validation → WPQR → deploy

## Accrued Income Status (2026-03-05)
- See [accruedincome-status.md](accruedincome-status.md) for full details
- Flask app at `/Users/pjbhb/accruedincome`, 5 blueprints, SQLite
- Phases 1-2 complete, Phase 3 (AI) not started
- Recent: added delete closing date feature (deployed, not yet committed to git)
- Git remote switched to SSH after 2FA setup
- User pending: run 2026-02-28 calculation

## Heatsim Status (2026-06-10)
- See [heatsim-status.md](heatsim-status.md) for full details
- Flask app, port **5004** locally, dual DB (users.db + materials.db with `__bind_key__='materials'`)
- **683 tests passing**; ruff clean; TRB-style verify scaffold in `.claude/scripts/`
- Deployed on server at `~/heatsim/`, container `app_portal-heatsim-1` (port 5002 internal, portal `/app/heatsim/`)
- 2026-06-10 committed (`3b5976af9` baseline, `ee1639760` features) + DEPLOYED: materials curve table editor + validation, interactive Plotly result plots (`/plot-data/<kind>` endpoint), bug sweep (ownership checks, t8/5 div-by-zero, safe form parsing, job error messages)

## MG5integration Status (2026-02-27)
- See [mg5integration-status.md](mg5integration-status.md) for full details
- Monitor G5 ERP data → SQLite → REST API for Accrued Income & SPInventory
- Excel upload module deployed: single-file per table + multi-file auto-detect
- Currently in **user testing period** — awaiting feedback
- 14 data tables, 68 tests passing, data loaded (86k verifications, 1.4k accounts, etc.)
- Key fix: `find_file_for_key()` prefers canonical uploaded filenames over old pattern matches

## TRB Status (2026-05-21)
- See [trb-status.md](trb-status.md) for full details
- [feedback_trb_kept_files.md](feedback_trb_kept_files.md) — keep root `.docx` template + `trb-context-doc-2.md` tracked, don't propose cleanup
- Flask app at `/Users/pjbhb/TRB`, port **5008**, deployed on server via Docker
- Own git repo since 2026-04-27; latest commit `510cbf4` on `main`, no remote, working tree clean
- Phases 1-3 complete + smoke tests (`tests/test_smoke.py`, 7 tests) + ruff/pytest config
- 2026-05-19 fix: review page is one multipart form, two submit buttons via `formaction`; `finalize` saves attached files via `_save_uploaded_files()` (guards on `FileStorage.filename`)
- Deploy: rsync `/Users/pjbhb/TRB/` → `administrator@172.27.55.104:/home/administrator/trb/` (exclude `.git/`, `__pycache__/`, `.ruff_cache/`, `.pytest_cache/`, `instance/`, `trb_output/`, `.DS_Store`, `.claude/`); then `cd /home/administrator/app_portal && docker compose build trb && docker compose up -d trb`
- Reads from Durabler2 DB (SQLAlchemy binds, read-only) + own `trb.db` for TRB register
- Word template with `{PLACEHOLDER}` markers (incl. SDT/textbox/core properties); `{CERT_LIST}` also under section 3 (2026-04-22)
- **Next**: bulk TRB generation paused; email distribution + per-customer templates queued

## SubseaCalc Status (2026-05-21)
- See [subcalc-status.md](subcalc-status.md) for full details
- Architecture decisions (Q1-Q6 all locked, Q5 + Q6 resolved): [subcalc-architecture-decisions.md](subcalc-architecture-decisions.md)
- Context doc: `/Users/pjbhb/subcalc/docs/subseacalc-context-doc-v0.1.md`
- Flask app at `/Users/pjbhb/subcalc`, port **5009** (moved from 5008 to avoid TRB clash), admin/admin login
- **DEPLOYED** to app_portal on subseavm01 at `https://172.27.55.104:8443/app/subcalc/`; portal `Application` row id=9, icon `bi-rulers`, display_order 71
- WPQR module deferred to future phase per 2026-05-06 deploy decision
- subcalc has its **own git repo** since 2026-06-09 (initial commit `e59059a` on `main`, no remote, 125 files); legacy `SubseaCalc/` (430MB binaries) + `SubseaCalc.zip` + `instance/` DB are gitignored. Nested inside home repo, which still lists it as `?? subcalc/`
- **Phase 2 COMPLETE** (all 8 sub-phases): **372 tests pass**, verify gate green
  - 2.1 Schema + import (~580k rows in 36s, 13/13 validations)
  - 2.2 Paginated browse views (Project list refactored from tree to paginated table)
  - 2.3 Inventor .txt exporter with byte-compare golden test (`tests/golden/test_provritning.txt`)
  - 2.4 Material module (Q6 archaeology: zero hardcoded customer branches in legacy → no CustomerRule table needed)
  - 2.5 Cost.xlsx template-fill exporter (writes to Item data input layer; preserves Subseatec formulas)
  - 2.6 Quote .docx generator (python-docx, builds from scratch — no legacy template)
  - 2.7 Designer-calc + read-only SVG render; Q5 TFS310 table externalized to `app/data/tfs310.json`
  - 2.8 Legacy Designer → Flask sync bridge: per-product .mdb re-import + JSON ingest (schema v1)
- 19+ SQLAlchemy models, 14 blueprints (auth/main/projects/material/admin/designer/cost/export + 6 more)
- Importer at `app/services/mdb_importer.py` with `import_product_by_key` + `import_product_from_json` (Phase 2.8)
- One-shot script at `scripts/import_legacy_mdb.py`; production templates at `app/templates/excel/Cost.xlsx`
- C++ source ref: `SubseaCalc/Source/SubseaCalc_2011_12_29/`
- Docs: `docs/legacy-mdb-snapshot.md`, `legacy-model-gap-analysis.md`, `legacy-designer-bridge.md`
- TRB-style verify scaffold: `tests/test_smoke.py`, `pyproject.toml`, `.claude/scripts/{verify,format-on-edit,guard-bash,session-context}.sh`
- Phase 3 candidates: validation against legacy oracle (Wine/VM), WPQR module, deploy

## HTtracker Status (2026-05-19)
- See [httracker-status.md](httracker-status.md) for full details
- Heat Treatment Tracker — another developer's Flask app, adapted for portal + deployed on server
- Local: `/Users/pjbhb/HTtracker`, server: `~/HTtracker`, container port 5007, URL `/app/heattreattracker/`
- Has its **own git repo** since 2026-06-09 (initial commit `a9184e7` on `main`, no remote, 13 files); DB/uploads/generated certs gitignored, `heattreatmenttemplate.docx` tracked. Nested inside home repo (`?? HTtracker/`)
- Fresh DB on server (user chose not to migrate local records); awaiting user end-to-end test via portal

## Durabler2 Status (2026-06-16)
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

# Familjekontor Project Memory

## Architecture
- Flask app with SQLAlchemy, Flask-Migrate, Flask-Login, Flask-WTF
- Config: `config.py` (dev/test/prod), TestingConfig uses separate SQLite DB
- Pattern: models → services → forms → routes (blueprints) → templates
- Each module: `app/models/`, `app/services/`, `app/forms/`, `app/routes/`, `app/templates/`
- BAS kontoplan in `app/utils/bas_kontoplan.py`
- Run on port **5004** (5000 is occupied)
- 34 blueprints (incl. notification_bp, batch_bp, favorites_bp, realestate_bp), 290+ routes, **1218 tests** (all passing)
- Git root is `/Users/pjbhb` (not `/Users/pjbhb/familjekontor`)
- TRB-style toolchain installed + ruff baseline at commit `a85d262f8` — see [familjekontor-toolchain.md](familjekontor-toolchain.md)

## Completed Phases
- **Phase 1**: Core accounting (companies, fiscal years, accounts, verifications, invoices, SIE, reports)
- **Phase 2**: Tax & compliance (VAT reports, deadlines, employer tax, tax payments)
- **Phase 3**: Salary & pension (employees, salary runs, PAYE tax, employer contributions 31.42%, ITP1/ITP2 pension, AGI/Collectum reporting)
- **Phase 4**: Extended features (4A-4K, see Phase 4 Details)
- **Phase 5**: Advanced features (5A-5G, see Phase 5 Details)
- **Phase 6**: Advanced reporting (6A-6E, see Phase 6 Details)
- **Phase 7**: UX & Productivity (7A-7E, see Phase 7 Details)

## Phase 4 Details
- **4A**: `dashboard_service.py` (KPIs, trends, aging, salary overview), Chart.js via CDN, 2 JSON API endpoints
- **4B**: `BankAccount`/`BankTransaction` models, CSV parsing (seb/swedbank/generic), auto-match by amount+date, 10 endpoints
- **4C**: `BudgetLine` model, grid editor with JS fetch save, variance analysis, forecast, Excel export, 8 endpoints
- **4D**: Document model extended with verification/invoice FKs, drag-drop upload JS, inline preview, 10 endpoints
- **4E**: `ConsolidationGroup`/`Member`/`Elimination` models, consolidated P&L/balance weighted by ownership_pct, 9 endpoints
- **4F**: `InvoiceLineItem` model, weasyprint PDF generation, self-contained invoice HTML template, 5 endpoints
- **4G**: Auto-create payment verifications when marking invoices as paid
- **4H**: Betalningsöversikt (payment overview) — unified view of paid supplier/customer invoices + tax payments, filterable by type/date, summary cards, verification links
- **4I**: Årsbokslut (year-end closing) — close result accounts (3xxx-8xxx) to 2099 Årets resultat, auto-create next FY + opening balances, FY lock prevents new verifications in closed years, preview page with summary cards, 3 routes, 11 tests
- **4J**: Multi-currency support — ExchangeRate model, Riksbanken SWEA API fetch, SEK-in-ledger pattern, FX gain/loss (6991/3960) on payment, currency_bp with rate management UI, AJAX rate auto-fill on invoice forms, 4 routes + 1 JSON API, 31 tests
- **4K**: Recurring invoices — `RecurringInvoiceTemplate`/`RecurringLineItem` models, manual generation trigger (no scheduler), copies template lines → `CustomerInvoice`+`InvoiceLineItem`, date advancement (monthly/quarterly/yearly with month-end clamping), recurring_bp with 12 routes, dashboard due count badge, 27 tests

## Phase 5 Details
- **5A**: AnnualReport model, K2-compliant årsredovisning with förvaltningsberättelse, flerårsöversikt, P&L, balance sheet, notes, signatures, WeasyPrint PDF, 6 routes, 15 tests
- **5B**: FixedAsset/DepreciationRun/DepreciationEntry models, straight-line & declining balance depreciation, auto-verification creation, asset disposal with gain/loss (3973/7973), K2 asset note in annual report, ASSET_CATEGORY_DEFAULTS dict, 8 routes, 32 tests
- **5C**: Governance & shareholders — BoardMember/ShareClass/Shareholder/ShareholderHolding/DividendDecision/AGMMinutes models, ownership summary with vote %, aktiebok (share register), dividend payment creates verification (Debit 2898, Credit 1930), AGM minutes, annual report board member integration (governance data with text fallback), ownership pie chart (Chart.js), 15 routes, 42 tests
- **5D**: Investment/portfolio management — InvestmentPortfolio/InvestmentHolding/InvestmentTransaction models, Nordnet CSV import (Latin-1, semicolon, Swedish numbers), weighted average cost method, realized gain/loss on sell, auto-verification per transaction type (köp/sälj/utdelning/ränta/avgift/insättning/uttag), portfolio summary with unrealized gains, dividend income report, 8 routes, 27 tests
- **5E**: Group consolidation enhancements — IntercompanyMatch/AcquisitionGoodwill models, auto-detect intercompany transactions (1660 vs 2360), confirm/reject matches creating eliminations, minority interest calc with ownership chain walking, consolidation methods (full/equity/cost), goodwill registration + K2 amortization (max 60 months), consolidated cash flow (indirect method), enhanced Excel export, 6 new routes, 24 tests
- **5F**: Deklaration (yearly tax return) — TaxReturn/TaxReturnAdjustment models, INK2 (AB, 20.6%) and INK4 (HB, pass-through), auto-populate from P&L accounts, manual tax adjustments (non-deductible/non-taxable/depreciation diff/deficit), custom adjustment line items, submit/approve lifecycle, Excel export, 12 routes added to tax_bp, 24 tests
- **5G**: Local AI/LLM support — Ollama integration (ai_client.py), Tesseract OCR (ocr.py), ai_service.py (invoice analysis, account suggestion with 20+ BAS patterns, NL financial queries with keyword routing, annual report text generation), ai_bp with chat UI + AJAX endpoints (query/suggest-account/analyze-invoice/status), graceful degradation when AI unavailable, 39 tests

## Key Patterns
- `_get_active_context()` returns (company_id, company, active_fy) in routes
- `@login_required` + `current_user.is_readonly` checks
- `AuditLog` for create/update/delete/approve actions
- `accounting_service.create_verification()` for balanced verifications (checks FY is open)
- `_create_verification_no_lock_check()` internal helper for closing/opening verifications
- Templates extend `base.html`, use Bootstrap 5.3 + Bootstrap Icons
- Swedish labels throughout (Jinja templates, form labels, flash messages)

## Migration Notes
- SQLite: `batch_alter_table` needed for FK changes, can fail with unnamed constraints
- If migration partially applies (tables created but stamp fails), use `flask db stamp <revision>`
- Remove auto-detected unrelated changes from migration files before applying
- Name FK constraints explicitly in migrations for SQLite compatibility
- Circular FKs (documents↔supplier_invoices): use `use_alter=True` on one side

## Lessons Learned
- When models have circular FKs, add `foreign_keys=[col]` to relationships and use unique backref names
- Edit tool fails on duplicate matches — use Write to rewrite entire file if needed
- Always verify active_company_id is in session before expecting dashboard content
- Admin password was reset to 'admin' during testing
- Route parameter names must match exactly in `url_for()` — e.g. `verification_id` not `id` (caused BuildError in payment overview)
- `get_trial_balance()` now includes `account_id` in returned dicts (needed for closing verification rows)
- Closing service uses `_create_verification_no_lock_check()` to write closing+opening verifications before/after setting FY status to 'closed'
- Account 2099 (Årets resultat) is auto-created if missing during closing
- Accounts 6991 (Valutakursförluster) and 3960 (Valutakursvinster) are auto-created during FX payment
- Riksbanken SWEA API: series IDs like SEKEURPMI, returns 1 SEK = X foreign, invert for 1 foreign = X SEK
- VerificationRow now supports optional currency metadata (currency, foreign_amount_debit/credit, exchange_rate)
- When adding new form fields (e.g. currency SelectField), update both service calls AND existing tests that POST to that form

## Asset Management Patterns
- `_ensure_account()` helper auto-creates BAS accounts if missing (used for depreciation/disposal)
- Depreciation runs: generate (pending) → post (creates verification) → status tracking
- Asset disposal books: Debit bank, Credit asset, Debit accumulated, +/- gain/loss accounts
- `get_accumulated_depreciation()` queries posted DepreciationEntry records
- `ASSET_CATEGORY_DEFAULTS` dict maps category → (asset_acct, depr_acct, expense_acct, life_months)
- Asset note data integrates into annual report PDF and view templates

## Governance Patterns
- Board members: active_only filter (end_date IS NULL), annual report uses FY date range
- Share classes with votes_per_share for dual-class structures (A/B shares)
- Ownership summary calculates both share % and vote % per shareholder
- Dividend flow: create decision (beslutad) → pay (betald, creates verification)
- Annual report: governance board data takes priority over text field fallback
- `get_board_for_annual_report()` filters by appointed_date <= fy.end_date AND (end_date IS NULL OR end_date >= fy.start_date)

## Investment Patterns
- Verification rules: köp→Debit ledger_acct/Credit 1930, sälj→Debit 1930/Credit ledger_acct + gain(8220)/loss(8230), utdelning→Debit 1930/Credit 8210, ränta→Debit 1930/Credit 8310, avgift→Debit 6570/Credit 1930
- Weighted average cost: on buy new_avg = (old_total_cost + new_cost) / new_qty; on sell cost_basis = avg_cost * qty
- Nordnet CSV: Latin-1 encoding (fallback UTF-8/CP1252), semicolon delimiter, Swedish number format (comma decimal, space thousands)
- `_get_or_create_holding()` matches by ISIN first, then by name within portfolio
- Holdings set active=False after full disposal (quantity reaches 0)
- `import_nordnet_transactions()` deduplicates by date+type+amount+name combination
- VP-only movements (splits, emissions, fissions) are skipped during import — use `adjust_holding()` to manually correct quantities
- `adjust_holding()` creates a `justering` transaction (amount=0) for audit trail, no accounting verification
- `delete_holding()` removes holding + transactions, blocked if any tx has linked verification
- Transaction types: kop, salj, utdelning, ranta, avgift, insattning, uttag, utlan, amortering, kupong, **justering**
- 50 investment tests total
- Spurious documents FK appears in every migration — always remove `batch_alter_table('documents')` blocks

## Consolidation Enhancement Patterns
- Intercompany detection: scans 1660-1662 (receivable) vs 2360-2362 (payable) across member pairs, uses per-company FY IDs
- Payable accounts (2xxx) need sign inversion: balance = credit - debit (not debit - credit)
- Ownership chains: `calculate_effective_ownership()` walks parent_member_id chain, multiplies percentages
- Consolidation methods: full (weight=1.0), equity (weight=ownership%), cost (weight=0 for P&L)
- Goodwill = purchase_price - (net_assets * ownership%), amortized linearly
- Cash flow: indirect method, compares current vs prior year balance sheets
- Route tests: use `logged_in_client` fixture (not manual `/auth/login` POST). Auth blueprint has NO prefix.

## INK Form Reporting (Skatteverket)
- `ink_form_service.py` — computes INK2R/INK2S/INK2/INK4R/INK4S on-the-fly from trial balance (no DB migration)
- BAS→INK field mappings: `INK2R_BS_FIELDS` (~50 balance sheet), `INK2R_IS_FIELDS` (~20 income statement)
- Each field: `(label, [account_prefixes], sign, sru_code)` — sign='debit' for assets, 'credit' for liabilities/equity/revenue, 'net' for mixed
- Subtotals computed from field groups (BS_SUBTOTALS, IS_SUBTOTALS dicts)
- Reuses `_sum_accounts()` from `deklaration_service` for account balance queries
- INK2S maps TaxReturn adjustments → fields 4.1-4.16 (result, non-deductible, non-taxable, depreciation diff, deficit)
- INK2 huvudblankett: field 1.1=överskott, 1.2=underskott (from INK2S 4.15/4.16)
- INK4 variant: same structure, different equity treatment, no corporate tax
- SRU file: ISO-8859-1 encoded, `#DATABESKRIVNING` header, `#BLANKETT INK2R-{year}P4`, `#FLT sru_code value` per field
- PDF: WeasyPrint with ink2_pdf.html (blue #003366) / ink4_pdf.html (green #2d5016), 4 pages each
- Web view: ink_view.html with 5 Bootstrap tabs (Översikt, Balansräkning, Resultaträkning, Justeringar, Huvudblankett)
- 3 routes: deklaration_ink_view, deklaration_ink_pdf, deklaration_sru_export
- 33 tests covering BS fields, IS fields, INK2S, INK2 main, SRU export, INK4, routes

## Deklaration Patterns
- P&L extraction: _sum_accounts() with prefix list and sign (debit/credit)
- BAS financial income: 80xx-83xx; financial expenses: 84xx-89xx (NOT 84 in income!)
- Personnel costs: 70xx-77xx; Depreciation: 78xx
- Tax rate: AB=20.6%, HB/EF=0% (pass-through)
- Lifecycle: draft → submitted → approved (submitted prevents edits)
- Adjustment line items sync totals to add/deduct fields on TaxReturn
- Routes added to existing tax_bp (no new blueprint)

## AI/LLM Patterns
- Ollama API: `/api/tags` for health/models, `/api/generate` for text generation
- All AI functions use `urllib.request` (no external deps), return None when unavailable
- Config: OLLAMA_ENABLED (default False), OLLAMA_HOST, OLLAMA_MODEL (llama3.2), OLLAMA_TIMEOUT
- Account suggestion: ACCOUNT_PATTERNS dict with regex → (BAS account, name), use `\b` word boundaries to avoid false matches (e.g. `\bel\b` for electricity, not matching "Telia")
- Invoice regex: `r'[Ff]aktura\s*nr?\.?\s*[:.]?\s*(\S+)'` handles "Faktura nr:", "Fakturanr:", etc.
- NL query routing: keyword-based (use stems like 'faktur' not 'faktura' to match 'fakturor' too)
- Tesseract OCR: lazy imports for pytesseract/PIL/pdfplumber (optional deps)
- ai_bp registered at `/ai` prefix, CSRF exempted for JSON endpoints

## Phase 6 Details
- **6A**: Financial Ratio Analysis — ratio_service.py (profitability/liquidity/solvency/efficiency), multi-year trend, traffic-light summary, ratios_bp with 2 routes, Chart.js horizontal bar + line charts, 24 tests
- **6B**: Cash Flow Statement — cashflow_service.py (indirect method: operating/investing/financing), monthly classification by 19xx counterpart, 3-month rolling avg forecast, Excel export, cashflow_bp with 3 routes, 22 tests
- **6C**: Period Comparison & Drill-Down — comparison_service.py (side-by-side FY comparison, YoY multi-year, account drilldown with running balance), clickable account numbers in P&L/BS, comparison_bp with 4 routes, 25 tests
- **6D**: AR/AP & Customer/Supplier Analysis — arap_service.py (aging buckets, DSO/DPO, top customers/suppliers, revenue breakdown doughnut), arap_bp with 6 routes, 28 tests
- **6E**: Report Center & PDF Export — SavedReport model, report_center_service.py (available reports catalog, CRUD saved configs, WeasyPrint PDF generation for pnl/balance/cashflow/ratios/comparison), report_center_bp with 4 routes, 6 PDF templates, 17 tests

## Phase 6 Patterns
- Jinja2 dict key naming: NEVER use 'items' as a dict key (conflicts with dict.items() method in templates) — use 'line_items' instead
- Cash flow indirect method: result + depreciation(78xx) +/- working capital (receivables 15-16xx, inventory 14xx, payables 24-29xx)
- Monthly CF classification: query VerificationRow touching 19xx accounts, classify by counterpart prefix
- User model: use `role='admin'` in constructor (not `is_admin=True` — that's a read-only property)
- PDF templates: extend pdf_base.html with `@page { size: A4; margin: 20mm; }`, self-contained CSS
- Report center: WeasyPrint with graceful degradation (returns None when unavailable)

## Phase 7 Details
- **7A**: Global Search — search_service.py (8 entity types: verifications, supplier/customer invoices, accounts, documents, customers, suppliers, employees), debounced JS with Ctrl+K shortcut, grouped dropdown results, 23 tests
- **7B**: Notification Center — Notification model, 5 checker types (overdue invoices, upcoming deadlines, document expiry, budget variance, FY closing), on-demand generation on dashboard load, bell icon badge with polling, notification_bp with 5 routes, 24 tests
- **7C**: Batch Operations — batch_service.py (approve/delete/export), batch_bp with 7 POST routes, checkbox columns + toolbars on 4 list pages (verifications, supplier/customer invoices, documents), vanilla JS with CSRF, 27 tests
- **7D**: Favorites & Quick Actions — UserFavorite model, favorite_service.py (CRUD, toggle, reorder, seed defaults), favorites_bp with 6 routes, drag-and-drop management page, dynamic dashboard quick actions, 23 tests
- **7E**: Enhanced Tables & Breadcrumbs — breadcrumbs on 37 templates via render_breadcrumbs macro, sticky table headers (4 list pages), column visibility toggle with localStorage, CSV export for documents + employees, table_enhancements.js, 20 tests

## Phase 7 Patterns
- CSRF for AJAX: meta tag `<meta name="csrf-token">`, JS reads via `document.querySelector('meta[name="csrf-token"]').content`, sends as `X-CSRFToken` header
- Batch operations: comma-separated IDs in form POST, validate all belong to company_id
- Favorites: user-scoped (not company-scoped), MAX_FAVORITES=20, seed_default_favorites() on first dashboard visit
- Notification dedup: check existing by entity_type+entity_id+notification_type before creating
- Column visibility: localStorage key `col_vis_<pathname>`, dropdown with checkboxes per <th>
- Employee model field is `employment_start` (NOT `employment_date`)
- Reports P&L route is `/reports/pnl` (NOT `/reports/profit-and-loss`)
- Invoice list routes: `/invoices/supplier-invoices` and `/invoices/customer-invoices`
- After service commits, SQLAlchemy objects become detached — use `db.session.get(Model, id)` to re-query

## Company Features
- Address fields, logo upload, theme color already implemented in Phase 1
- Model has: street_address, postal_code, city, country, logo_path, theme_color
