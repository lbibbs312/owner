# MoveDefense Codebase Audit

## Scope

This audit covers the current Flask/Jinja MoveDefense checkout with focus on route state, cargo state, mileage, scans, media, manager report context, and PDF output. The immediate conclusion is that the app has useful pieces of shared logic, but manager-facing reports still assemble business meaning from multiple controller/template helpers instead of one domain context.

## Route And Driver Log Models

- `app/models/log.py` defines `DriverLog` in table `driver_log`.
  - Route identity: `driver_id`, `date`, `plant_name`, `created_at`.
  - Timing: `arrive_time`, `depart_time`, `dock_wait_minutes`.
  - Cargo fields: `load_size`, `depart_load_size`, `secondary_load`, `no_pickup`, `part_number`, `hot_parts`.
  - Operational flags: `maintenance`, `fuel`, `meeting`, `downtime_reason`.
  - Soft delete: `deleted_at`, `deleted_by_id`.
- `app/models/log.py` defines `DriverLogPhoto` in table `driver_log_photo`.
  - Links to `driver_log.id` and stores file metadata, source, note, uploader, and upload time.
  - `file_available` checks filesystem availability directly.
- `app/models/task.py` defines `Task` in table `task`.
  - Used for driver assignments, hot moves, and linked move context.
- `app/models/plant_transfer.py` defines `PlantTransfer` and `PlantTransferLine`.
  - Separate paperwork flow that can also appear in route/day evidence.

## DVIR, PreTrip, PostTrip, Mileage, And Shift Models

- `app/models/trip.py` defines `PreTrip` in table `pretrip`.
  - Truck and trailer: `truck_number`, `trailer_number`.
  - Date and shift: `pretrip_date`, `shift`.
  - Mileage source: `start_mileage`.
  - Audit/inspection fields: many DOT/DVIR booleans plus `damage_report`.
  - Soft delete: `deleted_at`, `deleted_by_id`.
- `app/models/trip.py` defines `PostTrip` in table `posttrip`.
  - Links to `pretrip.id`.
  - Mileage closeout: `end_mileage`, `miles_driven`, `remarks`.
- `app/models/trip.py` defines `ShiftRecord` in table `shift_record`.
  - Links `user_id` and optional `pretrip_id`.
  - Contains `start_time`, `end_time`, `total_hours`, driver signature, and timestamp.

## Cargo, Scan, Manifest, And Hot-Part Tables

There is no true shipper/manifest table linked to manager route review today. Current cargo proof comes from driver-entered route cargo fields and part scan tables.

- `app/models/part.py` defines `PartMaster` in `part_master`.
- `app/models/part.py` defines `PartAlias` in `part_alias`.
- `app/models/part.py` defines `PartScanEvent` in `part_scan_event`.
  - Links to `stop_id`, `driver_id`, optional `move_id`, optional `part_id`, optional damage/delay records.
  - Stores `truck_id`, `trailer_id`, `plant_id`, `scan_context`, `validation_status`, and timestamps.
- `app/models/part.py` defines `MovePart` in `move_part`.
- `app/models/part.py` defines `PartLocationHistory` in `part_location_history`.
- `app/models/part.py` defines hot-part workflow tables: `HotPartAlert`, `HotMove`, `HotPartPhoto`, `HotPartEvent`, `PartRouteProfile`, `ExternalDocument`.
- `app/services/parts.py` normalizes raw scans, creates/updates parts and aliases, validates scans against a route context, and records `PartScanEvent` plus `PartLocationHistory`.

## Photo And Media Attachment Tables

- `app/models/damage.py` defines `DamageReport` in `damage_report`.
  - Links to driver, task, driver log, plant transfer, and truck/trailer metadata.
  - `move_reference` is currently used to connect PreTrip-created damage reports back to `PreTrip #<id>`.
- `app/models/damage.py` defines `DamagePhoto` in `damage_photo`.
  - Links to `DamageReport` and stores file metadata.
- `app/models/log.py` defines `DriverLogPhoto` in `driver_log_photo`.
- `app/models/part.py` defines `HotPartPhoto` in `hot_part_photo`.

## Report Templates And PDF Generators

Templates:
- `templates/manager_route_review.html`: Manager Route Review print view. It renders header, blockers, mileage review, cargo review, photo/safety review, delay review, route detail table, and manager decision.
- `templates/driver_logs_print.html`: Driver route printout.
- `templates/view_driver_log.html`: manager-facing single day-log management readout and proof page.
- `templates/driver_logs.html`: driver/manager log listing and export links.
- `templates/pretrip_printable.html` and `templates/view_pretrip.html`: DVIR print/view surfaces.
- `templates/view_damage_report.html` and `templates/damage_evidence_packet.html`: damage evidence surfaces.

Generators and builders:
- `app/blueprints/manager/routes.py:_route_print_context()` collects manager route data.
- `app/blueprints/manager/routes.py:_manager_route_review_context()` derives manager report status, blockers, summary, mileage, cargo, delay, and photo review.
- `app/blueprints/manager/routes.py:_build_manager_route_review_pdf()` creates Manager Route Review PDF directly.
- `app/blueprints/driver/routes.py:_build_pretrip_pdf()` creates DVIR PDF.
- `app/blueprints/driver/routes.py:_build_driver_logs_pdf()` creates driver log PDF.
- `app/blueprints/driver/routes.py:_build_eod_pdf()` creates end-of-day PDF.
- `app/blueprints/driver/routes.py:_build_plant_transfer_pdf()` creates plant transfer PDF.
- `app/services/simple_pdf.py` is the low-level PDF drawing helper.

## Current Route, Cargo, Mileage, Scan, Media, And Approval Logic Locations

Route state:
- `app/services/load_state.py:build_driver_log_route_context()` is the strongest shared source. It calculates arrival cargo, departure cargo, unloaded-on-arrival, secondary drop, route action, warnings, and `state`/`class`.
- `app/services/load_state.py:current_load_after_logs()` calculates current cargo after a log list.
- `app/services/management_readout.py` separately decides active stop, open stop exception, route narrative, and critical exception state.
- `app/blueprints/manager/routes.py:_manager_route_review_context()` separately derives `route_status` from log departure/finalization state.
- `templates/manager_route_review.html` currently decides route row status with `log.depart_time`, and labels completed rows as `Active`.

Cargo state:
- `app/services/load_state.py` knows multi-stop cargo (`depart_cargo_desc`, `secondary_load`, `secondary_dropped_on_arrival`).
- `app/blueprints/manager/routes.py:_manager_cargo_review()` re-evaluates cargo issues from `secondary_not_dropped_reason()`, `route_problem_reason()`, and route flags.
- `app/blueprints/manager/routes.py:_manager_summary_sentence()` re-evaluates final unload and later cargo activity using its own helpers.
- `templates/manager_route_review.html` renders cargo status and still contains direct table decisions.

Mileage state:
- `app/blueprints/driver/routes.py:_total_miles_for_pretrips()` is used on driver print paths.
- `app/blueprints/manager/routes.py:_manager_calculate_mileage_record()` calculates beginning/end mileage and status for manager review.
- `app/blueprints/manager/routes.py:_manager_mileage_review()` scopes mileage records and creates a quality item.
- `templates/pretrip_printable.html` directly calculates and displays mileage difference.

Scan inclusion:
- `app/blueprints/manager/routes.py:_part_scan_events_for_logs()` scopes scans to current route log IDs.
- `app/blueprints/manager/routes.py:view_driver_log()` has a second direct scan query for day logs.
- `app/services/management_readout.py:cargo_review_events()` and `critical_cargo_review_events()` use their own status sets.
- `app/blueprints/manager/routes.py:_manager_cargo_review()` uses a separate status set and summary language.

Media/photo rendering:
- `app/blueprints/driver/routes.py:_save_damage_photo()` and `_save_driver_log_photo()` write files.
- `app/blueprints/driver/routes.py:_damage_photo_file_path()` and `app/blueprints/manager/routes.py:_driver_log_photo_file_path()` are separate filesystem helpers.
- `app/services/evidence_packet.py:_photo_rows()` performs another damage-photo existence check.
- `templates/view_pretrip.html`, `templates/pretrip_printable.html`, `templates/manager_route_review.html`, `templates/view_driver_log.html`, and PDF builders each decide their own image/fallback rendering.

Approval blockers:
- `app/blueprints/manager/routes.py:_manager_data_quality()` creates data quality rows.
- `app/blueprints/manager/routes.py:_manager_required_actions()` creates required action text.
- `app/blueprints/manager/routes.py:_manager_approval_blockers()` creates approval blocker rows.
- `app/blueprints/manager/routes.py:_manager_review_status()` decides top-level review status.
- `app/blueprints/manager/routes.py:_manager_summary_sentence()` creates summary conclusions from the same partial inputs again.

## Duplicated Or Conflicting Business Logic

1. Route status is calculated in at least four places:
   - `load_state.py` produces `route.state` and `route.class`.
   - `management_readout.py` decides `Completed`, `In Progress`, or `Needs Review`.
   - `manager/routes.py:_manager_route_review_context()` decides `Finalized`, `Finalization Required`, `Active`, or `No Route`.
   - `manager_route_review.html` decides row status and currently labels completed rows `Active`.

2. Cargo state is split between route context and manager review:
   - `load_state.py` correctly models primary plus secondary cargo.
   - `_manager_summary_sentence()` treats first final unload before last stop as suspicious unless later stops are classified as non-cargo. It does not have a first-class cargo cycle model, so normal Raleigh East plus PPL two-stop cargo can look like later suspicious cargo.
   - `_manager_cargo_review()` creates cargo approval copy separately from the route context.

3. Mileage pending versus correction is mixed:
   - `_manager_calculate_mileage_record()` can label missing PostTrip as `Pending`.
   - `_manager_mileage_review()` sets `blocks_approval=True` for pending mileage.
   - `_manager_approval_blockers()` always labels blocking mileage as `Mileage conflict / correction required`, even when the underlying status is pending.
   - `_manager_required_actions()` says `Correct route mileage before approving route` even for missing PostTrip.

4. Scan review status sets are duplicated:
   - `management_readout.py` has `REVIEW_SCAN_STATUSES` and `CRITICAL_SCAN_STATUSES`.
   - `manager/routes.py:_manager_cargo_review()` has another set for pending/failed scans.
   - `parts.py:_validation_for_scan()` has its own meaning for `recorded`, `valid`, `unexpected`, `needs_review`, and `pending_part`.

5. Photo rendering and file existence checks are duplicated:
   - Damage photos, stop photos, hot-part photos, pretrip damage evidence, manager route PDF image rendering, browser templates, and evidence packet all use different helper paths and fallback behavior.

6. Report context is not a single source:
   - `_route_print_context()` gathers raw records.
   - `_manager_route_review_context()` adds several derived meanings.
   - The template and PDF still make their own route and media decisions.

## Proposed Shared Domain Services

Create or refactor toward these services. The names are intentional and should become the only approved places for business meaning.

- `app/services/route_state_service.py`
  - Input: ordered `DriverLog` rows, route date, route finalized flag.
  - Output: stop states (`Completed`, `Current/Open`, `Needs correction`), active stop, finalization state, route completion state, and route-level summary flags.
  - Rule: current open last stop is active work, not a critical exception.

- `app/services/cargo_reconciliation_service.py`
  - Input: `DriverLog` rows plus `load_state.build_driver_log_route_context()` output.
  - Output: cargo cycles, normal multi-stop transfers, impossible cargo mismatches, cargo still onboard at destination, and cargo approval state.
  - Rule: Helios can load Raleigh East Load plus PPL Load; Raleigh East can drop its load and continue with PPL Load; PPL unload is normal.

- `app/services/mileage_service.py`
  - Input: selected route `PreTrip`/`PostTrip`/`ShiftRecord` records.
  - Output: `Pending`, `OK`, or `Correction required` with blocker severity.
  - Rule: missing PostTrip is pending, not correction required. Only impossible odometer math or out-of-range calculated mileage is correction required.

- `app/services/media_attachment_service.py`
  - Input: photo/damage/hot-part/pretrip records.
  - Output: normalized media attachment rows with URL, local file path, uploaded time, source workflow, and render fallback.
  - Rule: reports render image or show explicit file failed to render blocker.

- `app/services/scan_scope_service.py`
  - Input: route/stop/log IDs and candidate scan rows.
  - Output: only scans linked to current route stops/logs, classified consistently as clean/pending/critical/orphan/excluded.
  - Rule: old test scans, orphaned scans, archived scans, and scans not linked to current route/stop/log are excluded from current reports.

- `app/services/report_context_builder.py`
  - Input: driver, route date.
  - Output: one immutable manager report context object consumed by HTML, PDF, CSV, and Sheets export.
  - Rule: templates render fields only; they do not infer route/cargo/mileage/photo state.

## Regression Tests To Add Before Fixing

The next tests should be added before report logic is changed:

1. Multi-stop cargo normal case:
   - Helios loads Raleigh East Load plus PPL Load.
   - Raleigh East drops Raleigh East Load and departs with PPL Load.
   - PPL unloads PPL Load and departs empty.
   - Expected: no warning about later PPL cargo activity.

2. Open current stop:
   - Driver is currently at Paint Central with no departure.
   - Expected: Current Active Stop / On pace / Awaiting departure.
   - Not expected: critical exception or correction required.

3. Missing PostTrip:
   - PreTrip start exists, PostTrip end missing.
   - Expected: Mileage pending PostTrip.
   - Not expected: mileage correction required.

4. Completed rows:
   - Completed stops should show Completed.
   - Only current open stop should show Open or Current.
   - Not expected: every completed row marked Active.

5. Photo upload/render:
   - A photo uploaded to PreTrip, damage, stop proof, or cargo proof should render in every report that references it or show explicit file-failed-to-render copy.

6. Phantom scan records:
   - Old test scans, orphaned scans, archived scans, and scans not linked to current route stops/logs must not appear in current reports.

## Immediate Risk Findings From The Audit

- `templates/manager_route_review.html` labeled completed route detail rows as `Active` when `log.depart_time` existed.
- `_manager_summary_sentence()` could treat normal later secondary cargo unloads as suspicious because it did not reason over full cargo cycles.
- `_manager_approval_blockers()` and `_manager_required_actions()` did not distinguish pending PostTrip mileage from odometer correction.
- Manager report business logic lived in `manager/routes.py` helpers and templates instead of shared domain services.
- Existing scan scoping was better than before because `_part_scan_events_for_logs()` filtered by route log IDs, but scan classification still had duplicated status sets.

## Remediation Started In This Changeset

- Added `app/services/route_state_service.py` so route rows and current active stop state are calculated before HTML/PDF rendering.
- Added `app/services/cargo_reconciliation_service.py` so multi-stop primary/secondary cargo is treated as a normal cargo cycle instead of suspicious later activity.
- Added `app/services/mileage_service.py` so missing PostTrip mileage is pending and only impossible odometer math or out-of-range mileage is correction required.
- Added `app/services/scan_scope_service.py` so route reports include scans linked to the current route stop IDs only.
- Added `app/services/media_attachment_service.py` as the shared render contract for media availability and file-failed-to-render fallback handling.

## Done Criteria For This Refactor

- New regression tests exist for the above scenarios.
- Tests fail before the service fix and pass after it.
- Manager Route Review HTML and PDF consume a shared context object.
- Route detail rows get state from route-state service, not template conditionals.
- Cargo review consumes cargo reconciliation output, not duplicated route-table wording.
- Mileage pending and mileage correction are separate blocker categories.
- Scan evidence rows identify exact scan source when scans are real.
- Media attachments use one normalized render contract across HTML and PDF.
