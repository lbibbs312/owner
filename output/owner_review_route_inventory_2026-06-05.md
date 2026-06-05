# MoveDefense Owner Review Sweep - 2026-06-05

Read-only review of `/data/data/com.termux/files/home/owner`.

Scope covered:
- `driver/routes.py` route-by-route review
- `manager/routes.py` route-by-route review
- templates and frontend JS
- auth, permissions, driver/manager/admin boundaries
- forms and request validation
- models, migrations, constraints, impossible states
- `production_flow.py` and `route_map.py`
- dead routes, duplicate routes, unused templates/services/static files

Verification performed:
- Registered route inventory generated from `create_app().url_map`.
- Template/static references checked with AST/regex search and targeted Flask client checks.
- Service reviewer ran `PYTHONPATH=. .venv/bin/pytest tests/test_route_map.py tests/test_production_flow.py`: 62 passed, 277 warnings.
- No files in application behavior were edited.

## Highest-Risk Findings

1. File: `app/blueprints/auth/routes.py:81`, route `/register`
   Function: `register`
   Exact issue: public registration allows `role=management`; if `MANAGER_REGISTRATION_PIN` is unset it falls back to `"0000"`.
   Operational risk: a public user can create a manager account and access manager dashboards, route review, proof deletion, dispatch capture, and move requests.
   Smallest safe fix: fail closed when `MANAGER_REGISTRATION_PIN` is missing; preferably remove public manager self-registration and create managers through CLI/admin tooling.
   Tests needed: yes, unset PIN, wrong PIN, configured PIN.

2. File: `app/blueprints/public/routes.py:31`, routes `/operations-board`, `/production-flow-board`
   Function: `production_flow_board`
   Exact issue: live plant/production board is public and calls `build_floor_operations_snapshot()` and `build_production_flow_context()`.
   Operational risk: unauthenticated users can view operational plant, route, move, driver, and dispatch state.
   Smallest safe fix: require login and an explicit view-only plant-floor role/token, or redact sensitive plant-floor output before any public sharing.
   Tests needed: yes, unauthenticated denied and authorized viewer renders.

3. File: `app/blueprints/driver/routes.py:2857`, `3120`, `3528`, `3760`, `3815`, `3860`, `4056`, `4101`
   Functions/routes: `edit_pretrip_entry`, `edit_plant_transfer`, `edit_driver_log`, `record_driver_log_photo`, `record_part_scan`, `depart_driver_log`, `no_pickup_driver_log`, `pickup_driver_log`
   Exact issue: driver mutation routes verify ownership but do not consistently block historical or finalized route records.
   Operational risk: a driver can alter timestamps, cargo state, scans, photos, transfer proof, or departure data after closeout, weakening chain-of-custody and audit defense.
   Smallest safe fix: add one shared route-record mutation guard for ownership, same-day/current-active route, and not-finalized via `_route_finalized_for_driver_date`.
   Tests needed: yes, finalized and past-date mutations denied; current same-day active mutations allowed.

4. File: `app/blueprints/driver/routes.py:4300`, `4332`, `4359`
   Routes: `/start_shift`, `/end_shift`, `/mobile/end-route`
   Exact issue: routes accept GET and mutate shift/route state.
   Operational risk: browser restore, prefetch, accidental tap, or copied link can start/end a shift or finalize a route.
   Smallest safe fix: make state changes POST-only and convert visible UI actions to POST forms.
   Tests needed: yes, GET does not mutate and POST still does.

5. File: `app/blueprints/driver/routes.py:4562`, route `/driver_logs/<log_id>/request_review`
   Function: `request_manager_review`
   Exact issue: endpoint is missing from `DRIVER_ONLY_ENDPOINTS`, uses raw `DriverLog.query.get_or_404()`, and does not verify assigned driver ownership.
   Operational risk: any authenticated user can create manager-review events against another driver's stop.
   Smallest safe fix: add endpoint to `DRIVER_ONLY_ENDPOINTS`, use active logs, and require `log.driver_id == current_user.id`.
   Tests needed: yes, owning driver succeeds; other driver and manager denied.

6. File: `app/blueprints/manager/routes.py:2691`, route `/manager/tasks/<task_id>`
   Function: `manage_task`
   Exact issue: POST writes `task.assigned_to` from any integer without verifying it exists or belongs to a driver.
   Operational risk: dispatch can assign a move to a manager or nonexistent user, causing it to disappear from driver workflow.
   Smallest safe fix: allow `0` for unassigned; otherwise require `User.query.filter_by(id=assigned_id, role="driver").first()`.
   Tests needed: yes, valid driver, unassigned, manager id, nonexistent id.

7. File: `app/blueprints/manager/routes.py:1858`, `649`
   Functions/routes: `mark_exception_reviewed`, `_active_exception_items`
   Exact issue: resolving exceptions writes only an `ActivityEvent`; `_reviewed_exception_keys()` hides future issues by target/category without fixing source state.
   Operational risk: open damage, cargo, truck, hot-move, or route problems can vanish from manager visibility while unresolved.
   Smallest safe fix: split acknowledge from resolve; suppress only when the source state is actually closed/fixed or include a source-state fingerprint.
   Tests needed: yes, unresolved source remains visible until closed.

8. File: `app/blueprints/manager/routes.py:2034`, `1911`
   Functions/routes: `resolve_review`, `_pending_review_stop_ids`
   Exact issue: resolving a review accepts any log id and later subtracts any resolved event for that stop, even if no current request exists.
   Operational risk: stale/direct POST can pre-clear a future driver review request.
   Smallest safe fix: require latest `manager_review_requested` exists and is newer than latest resolve, ideally linked by request event id.
   Tests needed: yes, resolve without request fails; newer request after old resolve shows.

9. File: `app/blueprints/driver/routes.py:1324`, `1380`; `app/services/hot_parts.py:341`
   Functions: `_save_damage_photo`, `_save_driver_log_photo`, `save_hot_part_photo`
   Exact issue: uploaded proof files are saved without MIME/extension validation, content sniffing, file-size cap, or app `MAX_CONTENT_LENGTH`.
   Operational risk: fake or oversized proof can pollute evidence packets or consume storage.
   Smallest safe fix: shared proof-upload validator with max bytes, allowed image/PDF MIME and extension, magic sniff for photos, empty upload rejection.
   Tests needed: yes, valid image, invalid MIME/extension, empty, oversized.

10. File: `app/blueprints/manager/move_requests.py:360`, `471`, `496`, `521`
    Routes: assign, mark blocked, mark completed, cancel
    Exact issue: lifecycle actions mutate status and emit flow events without an allowed transition matrix.
    Operational risk: one move request can be completed and then cancelled, weakening queue truth and flow projections.
    Smallest safe fix: centralize allowed transitions; block transitions from `completed` and `cancelled` unless an explicit correction/reopen action with reason exists.
    Tests needed: yes, reject closed-state transitions and update permissive lifecycle tests.

11. File: `app/blueprints/messaging/sockets.py:16`
    Functions: SocketIO `connect`, `join`, `leave`, `chat_message`
    Exact issue: socket handlers never check `current_user.is_authenticated` and allow arbitrary room names.
    Operational risk: anonymous socket connects can error; authenticated users can write to arbitrary rooms.
    Smallest safe fix: reject unauthenticated connects and constrain rooms to allowed rooms or explicit memberships.
    Tests needed: yes, SocketIO anonymous rejection and allowed authenticated room behavior.

12. File: `app/services/role_session.py:22`, `app/blueprints/auth/routes.py:19`
    Function: `restore_role_user`, `load_user_for_blueprint`
    Exact issue: role-specific session design depends on Flask-Login request loader overriding `_user_id`; in normal Flask-Login resolution `_user_id` can win first.
    Operational risk: driver/manager same-browser tab separation is unreliable, causing wrong-role redirects and unreachable management branches inside driver routes.
    Smallest safe fix: either remove dual-role same-browser support or make role switching explicit before authorization checks.
    Tests needed: yes, one client with both role keys hits driver-only and manager routes as expected.

13. File: `app/blueprints/manager/routes.py:2128`, templates `manager_review.html:213`, `view_damage_report.html:81`
    Route: `/manager/damage-reports/<report_id>/delete`
    Exact issue: manager cleanup hard-deletes damage reports and cascades DB photo rows.
    Operational risk: cargo/damage proof can be destroyed from manager screen, leaving only an audit stub.
    Smallest safe fix: archive/close with reason while preserving evidence access; reserve hard delete for admin purge.
    Tests needed: yes, archived hidden from active review but still available to audit/evidence.

14. File: `app/blueprints/manager/routes.py:228`, `2412`; template `manager_route_review.html:83`
    Functions/routes: `_route_export_response`, `driver_route_attachment`
    Exact issue: "Save PDF" points to HTML print URL instead of `attachment_url`; activity lacks route-scoped target id.
    Operational risk: official review downloads are harder to prove later.
    Smallest safe fix: link to `attachment_url`; record driver/date/log ids or first log id in activity/export metadata.
    Tests needed: yes, link target and activity target assertions.

15. File: `app/extensions.py:35`; plain manager POST routes
    Exact issue: no global CSRF protection for many non-FlaskForm mutation forms.
    Operational risk: a manager browser can be induced to mutate dispatch state, delete proof, or hide review issues.
    Smallest safe fix: add `CSRFProtect` globally and tokens for plain forms, or convert to FlaskForm-backed handlers.
    Tests needed: yes, missing token rejected and valid token accepted for representative manager mutations.

16. File: `app/forms/trip.py:37`, `120`; `app/blueprints/driver/routes.py:2661`, `2803`, `2875`
    Exact issue: odometer fields accept negative, zero, missing, or absurd values.
    Operational risk: driver closeout and manager route approval can be blocked or distorted by bad odometer data.
    Smallest safe fix: add `NumberRange(min=1, max=<cap>)`, require active DVIR start mileage, keep posttrip delta guard.
    Tests needed: yes, negative/zero/huge start and end mileage.

17. File: `app/blueprints/driver/routes.py:1067`, `3072`, `3133`
    Function: `_plant_transfer_line_from_request`
    Exact issue: transfer `quantity` and `skids` are raw strings; remarks-only rows count as transfer lines.
    Operational risk: MAT-C/transfer paperwork can show malformed cargo and break receiving reconciliation.
    Smallest safe fix: require cargo detail plus positive quantity/skid count or LP IDs; reject negative/non-numeric values; normalize transfer time.
    Tests needed: yes, invalid quantity/skids, remarks-only row, valid LP row.

18. File: `app/blueprints/driver/routes.py:5570`, `5755`
    Routes: `/tasks/<id>/hot-proof`, `/tasks/<id>/complete`
    Exact issue: hot-part task completion can occur without scan or photo proof.
    Operational risk: chain-of-custody can say hot part complete while proof packet shows no proof.
    Smallest safe fix: require scan/photo proof before dropoff completion or require override reason that creates a manager-review blocker.
    Tests needed: yes, no proof, scan proof, photo proof, override.

19. File: `app/blueprints/manager/routes.py:2390`, `2412`, `2431`; `app/blueprints/driver/routes.py:540`
    Routes: manager route print/attachment/export and driver mobile date helpers
    Exact issue: malformed `?date=` is swallowed and replaced with today.
    Operational risk: a bad link can print/export the wrong route date unnoticed.
    Smallest safe fix: strict date parser for print/export/report actions; reject invalid dates with 400 or visible warning.
    Tests needed: yes, invalid-date coverage.

20. File: `app/blueprints/driver/routes.py:4191`, `4459`
    Routes: `/driver_logs_print`, `/end_of_day_print`
    Exact issue: GET preview routes write "printed" activity records before confirmed print/download.
    Operational risk: activity history overstates official record production.
    Smallest safe fix: rename activity as preview-generated or move true printed markers to explicit POST endpoints.
    Tests needed: yes, preview vs confirmed print activity.

21. File: `app/services/production_flow.py:1943`, `1568`
    Functions: `_flow_map_edges`, `_flow_ledger_counts`
    Exact issue: flow edges and ledger counts stay date-wide even when `build_production_flow_context(driver_id=...)` scopes requests/logs/transfers.
    Operational risk: driver mobile production fragment can show another driver's FlowEvent stream.
    Smallest safe fix: filter by scoped driver/log/route ids.
    Tests needed: yes, cross-driver leakage test.

22. File: `app/services/production_flow.py:1080`, `1710`
    Functions: `_issue_events`, node issue counts
    Exact issue: every `ExceptionEvent` on date is treated active, including resolved events.
    Operational risk: production flow keeps nodes blocked after driver/manager resolution.
    Smallest safe fix: filter to active/blocking event types or subtract resolved stop ids like route-map does.
    Tests needed: yes.

23. File: `app/services/route_map.py:969`, `1087`
    Exact issue: `route_context.true_exceptions` is collected but not fed into `derive_issues`.
    Operational risk: earlier stop missing departure after later stops can appear as normal active/needs-departure instead of impossible sequence.
    Smallest safe fix: emit a specific missing-departure issue for earlier open stops while preserving normal current-open-stop behavior.
    Tests needed: yes.

24. File: `app/services/route_map.py:949`, `1045`
    Exact issue: any same-driver, same-date plant transfer sharing stop plant can count as proof.
    Operational risk: unrelated transfer sheet can hide missing proof or unconfirmed drop.
    Smallest safe fix: require explicit linked transfer/document proof or tighter lane/cargo/trailer/time-window matching.
    Tests needed: yes.

25. File: `app/services/route_map.py:721`, `app/services/production_flow.py:1010`
    Exact issue: active move requests are included regardless of selected date.
    Operational risk: historical replay can be polluted with today's open move queue.
    Smallest safe fix: split current active queue from date-scoped route snapshot, or include only due/requested/linked dates intersecting context date.
    Tests needed: yes.

26. File: `app/services/production_flow.py:1372`, `1762`, `1766`
    Exact issue: read-only/plant-floor context emits raw move descriptions, internal ids, and driver names even when permissions are false.
    Operational risk: public/read-only board leaks sensitive dispatch and driver data.
    Smallest safe fix: redact plant-floor/read-only view model or require auth.
    Tests needed: yes.

27. File: `app/blueprints/driver/routes.py:5806`, route `/map`
    Exact issue: route renders `map.html`, but the template does not exist.
    Operational risk: direct GET 500.
    Smallest safe fix: delete/redirect route or add real map template.
    Tests needed: yes.

28. File: `templates/direct_messages.html:30`, route `/direct_messages`
    Exact issue: calls `url_for('reply_dm')`; no registered endpoint exists.
    Operational risk: inbox render 500 when at least one message exists.
    Smallest safe fix: remove reply link or add `messaging.reply_dm`.
    Tests needed: yes.

29. File: `app/blueprints/public/routes.py:20`, route `/OneSignalSDKWorker.js`
    Exact issue: sends `static/OneSignalSDKWorker.js`, but file is absent; existing asset path is different.
    Operational risk: push service worker install fails.
    Smallest safe fix: place worker at served filename or remove/change SDK snippet.
    Tests needed: yes.

30. File: `app/services/production_flow.py:1444`, template `partials/_production_flow_drawer.html:162`
    Exact issue: plant-transfer and issue flow items have `view_url=None`; damage links can point to driver route even on manager board.
    Operational risk: manager drawer shows "Not wired yet" for real proof/issues or routes through wrong role.
    Smallest safe fix: manager mode should emit manager URLs for transfers, damage, driver logs, and reviews.
    Tests needed: yes.

31. File: `app/services/route_map.py:845`, template `partials/_move_detail_drawer.html:25`
    Exact issue: manager move action `View audit/proof` has `url=None`.
    Operational risk: proof path is advertised but unreachable.
    Smallest safe fix: link to real move request/evidence surface or remove disabled action.
    Tests needed: yes.

32. File: `app/services/route_map.py:850`, template `partials/_stop_detail_drawer.html:49`, `app/blueprints/driver/routes.py:581`
    Exact issue: stop actions render disabled `Record arrival` and `Add note`; `_route_cta_urls()` maps `add_note` to damage report.
    Operational risk: driver delay notes are impossible or misfiled as damage.
    Smallest safe fix: implement a log-note endpoint tied to `DriverLog`, or remove note controls and bad CTA mapping.
    Tests needed: yes.

33. File: `templates/manager_dashboard.html:466`, `1282`
    Exact issue: `Print Audit Log` opens `currentManageAction`, which is edit/detail URL, not audit/print URL.
    Operational risk: dispatcher lands on edit/detail screen and may think proof print happened.
    Smallest safe fix: pass separate `audit_print_url` and `record_url`, or remove modal print button.
    Tests needed: browser/UI test if kept.

34. File: `migrations/versions/39c678f87444_add_pretrip_boolean_fields.py:21`, `25a4fb5c8bb3_reordered_models.py:21`
    Exact issue: historical linear Alembic chain drops core tables and later recreates them.
    Operational risk: upgrading a nonempty old DB through that point destroys route logs, inspections, and messages.
    Smallest safe fix: replace destructive migration with non-destructive batch alters or hard guard on nonempty tables; provide current-schema baseline for new installs.
    Tests needed: yes, migration upgrade with seeded rows.

35. File: `app/models/log.py:9`, `app/services/route_context.py:145`
    Exact issue: `DriverLog` lacks durable `route_id`, `shift_record_id`, truck/trailer snapshot, and stop sequence; route identity is synthesized.
    Operational risk: same-driver/date multi-shift routes and proof attachments become ambiguous later.
    Smallest safe fix: add route/route_stop model or minimally add route id, shift id, stop sequence, truck/trailer snapshots with uniqueness.
    Tests needed: yes.

36. File: `app/models/part.py:57`, migration `fb1c2d3e4f5a_add_case_grouping_tables.py:35`
    Exact issue: `PartScanEvent.route_id`, `stop_id`, and `driver_log_id` are nullable and can disagree.
    Operational risk: stale scans can attach to route proof by broad scope.
    Smallest safe fix: require at least one strong scope, constrain `stop_id == driver_log_id` when both present, add indexes/FKs.
    Tests needed: yes.

37. File: `app/models/log.py:45`, migration `2c3d4e5f6071_add_driver_log_photo_document_fields.py:25`
    Exact issue: `DriverLogPhoto` has free-form nullable `owner_type`, `owner_id`, `document_type`, `review_status`.
    Operational risk: photo can claim to prove route/load/transfer while only attached to arbitrary stop.
    Smallest safe fix: constrain enums and add explicit nullable FKs for supported targets.
    Tests needed: yes.

38. File: `app/models/flow.py:26`, `32`
    Exact issue: offline idempotency is a plain index, not unique; `photo_id` and `document_id` are raw ints without FK.
    Operational risk: duplicate offline ledger events and missing evidence references.
    Smallest safe fix: partial unique constraint on `(tenant_id, device_id, offline_event_id)` and typed evidence FKs.
    Tests needed: yes.

39. File: `app/models/part.py:91`, `app/models/plant_transfer.py:42`
    Exact issue: cargo quantities and transfer lines lack DB checks for nonnegative math, duplicate line numbers, and empty lines.
    Operational risk: cargo reconciliation can certify impossible load math.
    Smallest safe fix: add checks for nonnegative values, picked/dropped <= expected, unique transfer line keys, and nonempty cargo line detail.
    Tests needed: yes.

40. File: `app/models/move_request.py:27`, `app/models/task.py:13`, `app/models/load_intent.py:22`, `app/models/part.py:149`, `app/models/damage.py:11`
    Exact issue: lifecycle states are free-form strings with independent reasons/timestamps/links.
    Operational risk: manager boards and reports can show final states with no proof.
    Smallest safe fix: status enums plus check constraints for required reason/timestamp/link combinations.
    Tests needed: yes.

41. File: `app/models/audit.py:10`
    Exact issue: `AuditEvent` uses free-form target type, raw integer id, text snapshots, no tenant/correlation, no tamper-evident protection.
    Operational risk: audit trail is ambiguous or unverifiable under dispute.
    Smallest safe fix: constrain target types, store structured JSON, add correlation IDs, prevent hard deletes or add hash chaining for critical events.
    Tests needed: yes.

42. File: `app/models/part.py:10`
    Exact issue: part canonical and alias values are indexed but not unique per tenant.
    Operational risk: same scanned cargo can map to two internal part identities.
    Smallest safe fix: unique constraints on `(tenant_id, canonical_part_number)` and `(tenant_id, normalized_value)` after dedupe.
    Tests needed: yes.

## Cleanup and Merge Findings

- `app/blueprints/driver/routes.py:5351`, `/dashboard`: driver-only route immediately redirects drivers to `/mobile`; remaining dashboard body and `templates/dashboard.html` are unreachable. Rank: FIX/DELETE.
- `app/blueprints/driver/routes.py:3622`: legacy driver URLs duplicate canonical `/driver_logs/...`; legacy pickup redirects to depart even though canonical pickup exists. Rank: MERGE/DELETE.
- Multi-rule endpoints: `/tasks` + `/list_tasks`, `/operations-board` + `/production-flow-board`, `/manager/trim` + `/manager/trim-dashboard`. Rank: MERGE.
- Unused templates with no render/include/extend/import refs found: `about.html`, `add_pretrip_entry.html`, `all_in_one_dashboard.html`, `create_task.html`, `do_posttrip.html`, `driver_dashboard.html`, `driver_weekly_performance.html`, `edit_pretrip.html`, `edit_task.html`, `editing_task.html`, `index.html`, `layout.html`, `list_driving_logs.html`, `manager_all_pretrips.html`, `manager_drivers.html`, `manager_tasks.html`, `new_tip.html`, `pdf_daily_logs.html`, `ppl_maintenance.html`, `pretrip.html`, `register_example.html`, `reply_dm.html`, `reply_message.html`, `task.html`, `tasks.html`, `unified_dashboard.html`, `weekly_performance.html`, `partials/_live_route_map.html`, `partials/_next_action_card.html`. Rank: DELETE after smoke check.
- `app/services/constraint_engine.py`: no references outside itself. Rank: DELETE or WIRE.
- `static/handoffTask.js`: unreferenced and fetches missing `/handoff_task`. Rank: DELETE or WIRE.
- `static/css/images/style.css` and `static/css/images/logo.png`: unreferenced except through unused `ppl_maintenance.html`. Rank: DELETE.

## Complete Registered Route Inventory

Legend:
- Auth: public, login, driver, management, management+debug.
- Data: read, mutate, static.
- Linked: local template/static endpoint or path reference found. This is not an external backlink crawl.

| Rank | URL | Methods | Function | Blueprint | Template | Auth | Data | Linked | Notes |
|---|---|---:|---|---|---|---|---|---|---|
| KEEP | `/` | GET | `welcome` | public | `welcome.html` | public | read | yes | Landing/welcome |
| FIX | `/OneSignalSDKWorker.js` | GET | `onesignal_sw` | public | - | public | static | no | Route serves missing worker file |
| KEEP | `/add_stop` | GET,POST | `add_stop` | driver | `add_stop.html` | driver | mutate | yes | Current arrival/add-stop flow |
| KEEP | `/announcements` | GET,POST | `announcements` | messaging | `announcements.html` | login | mutate | yes | POST management-only inside handler |
| FIX | `/chat` | GET | `chat_page` | messaging | `chat.html` | login | read | no | Orphaned from current nav; socket auth needs lock down |
| KEEP | `/count_unread` | GET | `count_unread` | messaging | - | login | read | yes | Notification API |
| KEEP | `/damage_reports` | GET | `damage_reports` | driver | `damage_reports.html` | driver | read | yes | Driver damage list |
| KEEP | `/damage_reports/<int:report_id>` | GET | `view_damage_report` | driver | `view_damage_report.html` | driver | read | yes | Driver owned report view |
| KEEP | `/damage_reports/<int:report_id>/delete` | POST | `delete_damage_report` | driver | - | driver | mutate | yes | Uses driver damage modify guard |
| KEEP | `/damage_reports/<int:report_id>/edit` | GET,POST | `edit_damage_report` | driver | `damage_report_form.html` | driver | mutate | yes | Uses damage modify guard |
| KEEP | `/damage_reports/<int:report_id>/evidence_packet` | GET | `damage_evidence_packet` | driver | `damage_evidence_packet.html` | driver | read | yes | Evidence packet |
| KEEP | `/damage_reports/<int:report_id>/submit` | POST | `submit_damage_report` | driver | - | driver | mutate | yes | Submit damage report |
| KEEP | `/damage_reports/new` | GET,POST | `new_damage_report` | driver | `damage_report_form.html` | driver | mutate | yes | Driver damage capture |
| KEEP | `/damage_reports/photos/<int:photo_id>` | GET | `damage_photo` | driver | - | driver | read | no | Photo response; proof upload validation issue is upstream |
| FIX | `/dashboard` | GET,POST | `dashboard` | driver | `dashboard.html` | driver | mutate | yes | Driver immediately redirects to `/mobile`; body unreachable |
| KEEP | `/debug/route-context/<path:route_id>` | GET | `debug_route_context` | public | - | management+debug | read | no | Already gated by role and debug flag |
| MERGE | `/depart_driver_log/<int:log_id>` | GET,POST | `legacy_depart_driver_log` | driver | - | login | mutate | no | Legacy redirect; add driver-role guard or delete |
| FIX | `/direct_messages` | GET,POST | `direct_messages` | messaging | `direct_messages.html` | login | mutate | yes | Inbox can 500 on nonexistent `reply_dm` link |
| KEEP | `/do_posttrip/<int:pretrip_id>` | GET,POST | `do_posttrip` | driver | `posttrip.html` | driver | mutate | yes | Needs same-day/finalized guard consistency |
| KEEP | `/drafts/autosave` | GET | `get_autosave` | drafts | - | login | read | yes | User-scoped draft read |
| KEEP | `/drafts/autosave` | POST | `save_autosave` | drafts | - | login | mutate | yes | User-scoped draft write; size cap exists |
| KEEP | `/drafts/clear` | POST | `clear_autosave` | drafts | - | login | mutate | yes | User-scoped draft delete |
| KEEP | `/driver_logs` | GET | `driver_logs` | driver | `driver_logs.html` | driver | read | yes | Main driver log list |
| KEEP | `/driver_logs/<int:log_id>/clear-hot` | POST | `clear_driver_log_hot_part` | driver | - | driver | mutate | yes | Same-day/finalized guard should be checked |
| LOCK DOWN | `/driver_logs/<int:log_id>/close_issue` | POST | `close_driver_log_issue` | driver | - | login | mutate | yes | Handler checks role/owner but missing driver endpoint guard |
| KEEP | `/driver_logs/<int:log_id>/delete` | POST | `delete_driver_log` | driver | - | driver | mutate | yes | Uses same-day guard |
| FIX | `/driver_logs/<int:log_id>/depart` | GET,POST | `depart_driver_log` | driver | `depart_driver_log.html` | driver | mutate | yes | Needs finalized/past-date guard consistency |
| KEEP | `/driver_logs/<int:log_id>/no_pickup` | POST | `no_pickup_driver_log` | driver | - | driver | mutate | yes | Needs finalized/past-date guard consistency |
| KEEP | `/driver_logs/<int:log_id>/part-scans` | POST | `record_part_scan` | driver | - | driver | mutate | yes | Needs proof scope constraints and finalized guard |
| KEEP | `/driver_logs/<int:log_id>/photos` | POST | `record_driver_log_photo` | driver | - | driver | mutate | yes | Needs upload validator and finalized guard |
| FIX | `/driver_logs/<int:log_id>/pickup` | GET,POST | `pickup_driver_log` | driver | `pickup_driver_log.html` | driver | mutate | no | Canonical route exists but legacy pickup redirects to depart |
| LOCK DOWN | `/driver_logs/<int:log_id>/request_review` | POST | `request_manager_review` | driver | - | login | mutate | yes | Missing driver-role/owner guard |
| KEEP | `/driver_logs/photos/<int:photo_id>` | GET | `driver_log_photo` | driver | - | driver | read | yes | Photo response |
| KEEP | `/driver_logs/photos/<int:photo_id>/delete` | POST | `delete_driver_log_photo` | driver | - | driver | mutate | yes | Needs finalized guard consistency |
| FIX | `/driver_logs_print` | GET | `driver_logs_print` | driver | `driver_logs_print.html` | driver | mutate | yes | GET logs printed activity before confirmed print |
| KEEP | `/driver_logs_print/attachment` | GET | `driver_logs_attachment` | driver | - | driver | read | no | Direct PDF attachment |
| FIX | `/edit_driver_log/<int:log_id>` | GET,POST | `edit_driver_log` | driver | `edit_driver_log.html` | driver | mutate | yes | Needs finalized/past-date guard consistency |
| MERGE | `/edit_driving_log/<int:log_id>` | GET,POST | `legacy_edit_driving_log` | driver | - | login | mutate | no | Legacy redirect; add driver guard or delete |
| FIX | `/edit_pretrip_entry/<int:pretrip_id>` | GET,POST | `edit_pretrip_entry` | driver | `edit_pretrip_entry.html` | driver | mutate | yes | Needs finalized/past-date guard consistency |
| FIX | `/end_of_day_print` | GET | `end_of_day_print` | driver | `end_of_day_print.html` | driver | mutate | yes | GET logs printed activity before confirmed print |
| KEEP | `/end_of_day_print/attachment` | GET | `end_of_day_attachment` | driver | - | driver | read | no | Direct PDF attachment |
| KEEP | `/end_of_day_summary` | GET,POST | `end_of_day_summary` | driver | `end_of_day_summary.html` | driver | mutate | yes | EOD workflow |
| FIX | `/end_shift` | GET,POST | `end_shift` | driver | - | driver | mutate | no | GET mutates shift state |
| KEEP | `/healthz` | GET | `healthz` | public | - | public | static | no | Health check |
| KEEP | `/knowledge_base` | GET,POST | `knowledge_base` | messaging | `knowledge_base.html` | login | mutate | yes | Cross-role knowledge base |
| KEEP | `/list_pretrips` | GET | `list_pretrips` | driver | `list_pretrips.html` | driver | read | yes | Driver pretrip list |
| MERGE | `/list_tasks` | GET | `list_tasks` | driver | `list_tasks.html` | driver | read | yes | Duplicate URL with `/tasks`; choose canonical |
| KEEP | `/login` | GET,POST | `login` | auth | `login.html` | public | mutate | yes | Auth route |
| KEEP | `/logout` | GET | `logout` | auth | - | login | mutate | yes | Clears role sessions |
| KEEP | `/manager/` | GET | `manager_root` | manager | - | management | read | yes | Redirect to dashboard |
| KEEP | `/manager/audit-history` | GET | `audit_history` | manager | `audit_history.html` | management | read | yes | Audit history |
| KEEP | `/manager/create_task_from_dashboard` | POST | `create_task_from_dashboard` | manager | - | management | mutate | yes | Dashboard task creation validates driver |
| LOCK DOWN | `/manager/damage-photos/<int:photo_id>` | GET | `damage_photo` | manager | - | management | read | yes | Proof media route |
| KEEP | `/manager/damage-reports/<int:report_id>` | GET | `view_damage_report` | manager | `view_damage_report.html` | management | read | yes | Manager damage view |
| FIX | `/manager/damage-reports/<int:report_id>/delete` | POST | `delete_damage_report` | manager | - | management | mutate | yes | Hard-deletes evidence |
| KEEP | `/manager/damage-reports/<int:report_id>/evidence-packet` | GET | `damage_evidence_packet` | manager | `damage_evidence_packet.html` | management | read | yes | Evidence packet |
| KEEP | `/manager/dashboard` | GET,POST | `manager_dashboard` | manager | `manager_dashboard.html` | management | mutate | yes | Main manager dashboard; CSRF/plain POST concerns |
| LOCK DOWN | `/manager/dispatch-captures` | POST | `create_dispatch_capture_route` | manager | - | management | mutate | yes | Plain POST; add CSRF |
| LOCK DOWN | `/manager/dispatch-captures/<int:capture_id>/convert` | POST | `convert_dispatch_capture_route` | manager | - | management | mutate | yes | Plain POST; add CSRF |
| LOCK DOWN | `/manager/dispatch-captures/<int:capture_id>/dismiss` | POST | `dismiss_dispatch_capture_route` | manager | - | management | mutate | yes | Plain POST; add CSRF |
| LOCK DOWN | `/manager/driver-log-photos/<int:photo_id>` | GET | `driver_log_photo` | manager | - | management | read | yes | Proof media route |
| LOCK DOWN | `/manager/driver-log-photos/<int:photo_id>/delete` | POST | `delete_driver_log_photo` | manager | - | management | mutate | yes | Plain POST proof delete; add CSRF/archive policy |
| KEEP | `/manager/driver-logs` | GET | `driver_logs` | manager | `driver_logs.html` | management | read | yes | Manager route log index |
| KEEP | `/manager/driver-logs/<int:log_id>` | GET | `view_driver_log` | manager | `view_driver_log.html` | management | read | yes | Manager stop view |
| KEEP | `/manager/driver-logs/route-attachment` | GET | `driver_route_attachment` | manager | - | management | read | no | Direct PDF; link issue in print template |
| FIX | `/manager/driver-logs/route-export` | GET | `driver_route_export` | manager | - | management | read | yes | Add route-scoped activity metadata |
| FIX | `/manager/driver-logs/route-print` | GET | `driver_route_print` | manager | `manager_route_review.html` | management | read | yes | Save PDF link points at HTML print |
| MERGE | `/manager/exceptions` | GET | `exceptions_dashboard` | manager | - | management | read | no | Redirect/merge into review |
| FIX | `/manager/exceptions/reviewed` | POST | `mark_exception_reviewed` | manager | - | management | mutate | yes | Activity-only hide of unresolved issues |
| LOCK DOWN | `/manager/followups/<int:followup_id>/close` | POST | `close_followup` | manager | - | management | mutate | no | Plain POST; add CSRF |
| LOCK DOWN | `/manager/hot-part-photos/<int:photo_id>` | GET | `hot_part_photo` | manager | - | management | read | yes | Proof media route |
| KEEP | `/manager/move-requests` | GET | `move_requests` | manager | `manager/move_requests.html` | management | read | yes | Move queue |
| FIX | `/manager/move-requests/<int:request_id>/acknowledge` | POST | `acknowledge_move_request` | manager | - | management | mutate | yes | Add transition matrix/CSRF |
| FIX | `/manager/move-requests/<int:request_id>/assign` | POST | `assign_move_request` | manager | - | management | mutate | yes | Add transition matrix/driver validation |
| FIX | `/manager/move-requests/<int:request_id>/cancel` | POST | `cancel_move_request` | manager | - | management | mutate | yes | Closed-state transition issue |
| KEEP | `/manager/move-requests/<int:request_id>/edit` | GET,POST | `edit_move_request` | manager | `manager/move_request_form.html` | management | mutate | yes | Durable edit path |
| KEEP | `/manager/move-requests/<int:request_id>/link-evidence` | POST | `link_move_request_evidence` | manager | - | management | mutate | yes | Evidence linking; add CSRF |
| FIX | `/manager/move-requests/<int:request_id>/mark-blocked` | POST | `mark_move_request_blocked` | manager | - | management | mutate | yes | Transition matrix needed |
| FIX | `/manager/move-requests/<int:request_id>/mark-completed` | POST | `mark_move_request_completed` | manager | - | management | mutate | yes | Transition matrix needed |
| KEEP | `/manager/move-requests/new` | GET,POST | `new_move_request` | manager | `manager/move_request_form.html` | management | mutate | yes | Creation path |
| KEEP | `/manager/move-requests/parse` | POST | `parse_move_request` | manager | - | management | read | no | Suggestion-only parser |
| KEEP | `/manager/plant-transfers` | GET | `plant_transfers` | manager | `plant_transfers.html` | management | read | no | Manager transfer list |
| KEEP | `/manager/plant-transfers/<int:transfer_id>` | GET | `view_plant_transfer` | manager | `view_plant_transfer.html` | management | read | yes | Transfer view |
| KEEP | `/manager/plant-transfers/<int:transfer_id>/attachment` | GET | `plant_transfer_attachment` | manager | - | management | read | no | Direct PDF attachment |
| LOCK DOWN | `/manager/plant-transfers/<int:transfer_id>/mark_printed` | POST | `mark_plant_transfer_printed` | manager | - | management | mutate | no | Plain POST; add CSRF |
| KEEP | `/manager/plant-transfers/<int:transfer_id>/print` | GET | `plant_transfer_printable` | manager | `plant_transfer_printable.html` | management | read | no | Printable transfer |
| KEEP | `/manager/pretrips` | GET | `list_pretrips` | manager | `list_pretrips.html` | management | read | yes | Manager DVIR list |
| KEEP | `/manager/pretrips/<int:pretrip_id>` | GET | `view_pretrip` | manager | `view_pretrip.html` | management | read | yes | Manager DVIR view |
| KEEP | `/manager/pretrips/<int:pretrip_id>/attachment` | GET | `pretrip_attachment` | manager | - | management | read | no | Direct PDF attachment |
| LOCK DOWN | `/manager/pretrips/<int:pretrip_id>/mark_printed` | POST | `mark_pretrip_printed` | manager | - | management | mutate | no | Plain POST; add CSRF |
| KEEP | `/manager/pretrips/<int:pretrip_id>/print` | GET | `pretrip_printable` | manager | `pretrip_printable.html` | management | read | no | Printable DVIR |
| FIX | `/manager/review` | GET,POST | `review_dashboard` | manager | `manager_review.html` | management | mutate | yes | Exception suppression and approval blockers need fix |
| KEEP | `/manager/reviews` | GET | `review_queue` | manager | `manager_reviews.html` | management | read | yes | Manager review queue |
| FIX | `/manager/reviews/<int:log_id>/resolve` | POST | `resolve_review` | manager | - | management | mutate | yes | Can pre-clear missing request |
| KEEP | `/manager/search/suggest` | GET | `search_suggest` | manager | - | management | read | yes | Search suggestions |
| FIX | `/manager/tasks/<int:task_id>` | GET,POST | `manage_task` | manager | `manager_task_detail.html` | management | mutate | yes | Assignment accepts any int |
| DELETE | `/manager/trim` | GET | `trim_dashboard` | manager | - | management | read | no | Duplicate legacy redirect, unlinked |
| DELETE | `/manager/trim-dashboard` | GET | `trim_dashboard` | manager | - | management | read | no | Duplicate legacy redirect, unlinked |
| DELETE | `/map` | GET | `show_map` | driver | `map.html` | driver | read | no | Missing template |
| KEEP | `/mobile` | GET | `mobile_dashboard` | driver | `driver_mobile.html` | driver | read | yes | Main driver mobile surface |
| FIX | `/mobile/end-route` | GET,POST | `mobile_end_route` | driver | - | driver | mutate | no | GET mutates route state |
| KEEP | `/mobile/history` | GET | `mobile_history` | driver | `mobile_history.html` | driver | read | yes | Driver history |
| KEEP | `/mobile/history/<report_date>` | GET | `mobile_day_report` | driver | `mobile_day_report.html` | driver | read | yes | Dated driver history; strict date parsing needed |
| FIX | `/mobile/production-flow-fragment` | GET | `mobile_production_flow_fragment` | driver | `partials/_production_flow_map.html` | login | read | no | Missing driver endpoint guard and cross-driver service leakage |
| FIX | `/mobile/route-map-fragment` | GET | `mobile_route_map_fragment` | driver | `partials/_compact_route_map.html` | login | read | yes | Missing driver endpoint guard |
| KEEP | `/mobile/ryder-service` | POST | `mobile_ryder_service` | driver | - | driver | mutate | yes | Ryder service workflow |
| KEEP | `/new_driving_log` | GET,POST | `new_driving_log` | driver | - | driver | mutate | yes | Creates route stop |
| KEEP | `/new_pretrip` | GET,POST | `new_pretrip` | driver | `new_pretrip.html` | driver | mutate | yes | DVIR creation |
| MERGE | `/no_pickup_driver_log/<int:log_id>` | POST | `legacy_no_pickup_driver_log` | driver | - | login | mutate | no | Legacy redirect; add driver guard or delete |
| LOCK DOWN | `/operations-board` | GET | `production_flow_board` | public | `plant_floor_board.html` | public | read | no | Live ops board public |
| MERGE | `/pickup_driver_log/<int:log_id>` | GET,POST | `legacy_pickup_driver_log` | driver | - | login | mutate | no | Legacy route redirects to depart, not canonical pickup |
| KEEP | `/plant_directory` | GET | `plant_directory` | public | `plant_directory.html` | login | read | yes | Directory |
| KEEP | `/plant_transfers` | GET | `plant_transfers` | driver | `plant_transfers.html` | driver | read | yes | Driver transfers |
| KEEP | `/plant_transfers/<int:transfer_id>` | GET | `view_plant_transfer` | driver | `view_plant_transfer.html` | driver | read | yes | Driver transfer view |
| KEEP | `/plant_transfers/<int:transfer_id>/attachment` | GET | `plant_transfer_attachment` | driver | - | driver | read | yes | PDF attachment |
| KEEP | `/plant_transfers/<int:transfer_id>/delete` | POST | `delete_plant_transfer` | driver | - | driver | mutate | yes | Needs finalized guard consistency |
| FIX | `/plant_transfers/<int:transfer_id>/edit` | GET,POST | `edit_plant_transfer` | driver | `plant_transfer_form.html` | driver | mutate | yes | Needs finalized guard and line validation |
| KEEP | `/plant_transfers/<int:transfer_id>/mark_printed` | POST | `mark_plant_transfer_printed` | driver | - | driver | mutate | no | Mark printed |
| KEEP | `/plant_transfers/<int:transfer_id>/print` | GET | `plant_transfer_printable` | driver | `plant_transfer_printable.html` | driver | read | yes | Printable transfer |
| KEEP | `/plant_transfers/new` | GET,POST | `new_plant_transfer` | driver | `plant_transfer_form.html` | driver | mutate | yes | Needs line validation |
| KEEP | `/pretrip_printable/<int:pretrip_id>` | GET | `pretrip_printable` | driver | `pretrip_printable.html` | driver | read | yes | Printable DVIR |
| KEEP | `/pretrip_printable/<int:pretrip_id>/attachment` | GET | `pretrip_attachment` | driver | - | driver | read | no | PDF attachment |
| KEEP | `/pretrip_printable/<int:pretrip_id>/mark_printed` | POST | `mark_pretrip_printed` | driver | - | driver | mutate | no | Mark printed |
| KEEP | `/pretrips/<int:pretrip_id>/delete` | POST | `delete_pretrip` | driver | - | driver | mutate | yes | Uses same-day guard |
| LOCK DOWN | `/production-flow-board` | GET | `production_flow_board` | public | `plant_floor_board.html` | public | read | no | Duplicate public ops board |
| KEEP | `/profile` | GET,POST | `profile` | driver | `profile.html` | driver | mutate | yes | Driver profile |
| KEEP | `/readyz` | GET | `readyz` | public | - | public | read | no | Readiness check |
| KEEP | `/recent_activity` | GET | `recent_activity` | messaging | dynamic | login | read | yes | Uses role-specific template |
| LOCK DOWN | `/register` | GET,POST | `register` | auth | `register.html` | public | mutate | yes | Manager self-registration fail-open |
| FIX | `/start_shift` | GET,POST | `start_shift` | driver | - | driver | mutate | no | GET mutates shift state |
| KEEP | `/submit_end_of_day` | POST | `submit_end_of_day` | driver | - | driver | mutate | no | EOD submit |
| MERGE | `/tasks` | GET | `list_tasks` | driver | `list_tasks.html` | driver | read | yes | Duplicate URL with `/list_tasks`; choose canonical |
| KEEP | `/tasks/<int:task_id>` | GET | `view_task` | driver | `driver_task_detail.html` | driver | read | yes | Driver task detail |
| KEEP | `/tasks/<int:task_id>/accept` | POST | `accept_task` | driver | - | driver | mutate | yes | Task accept |
| FIX | `/tasks/<int:task_id>/complete` | POST | `complete_task` | driver | - | driver | mutate | yes | Hot parts can complete without proof |
| KEEP | `/tasks/<int:task_id>/decline` | POST | `decline_task` | driver | - | driver | mutate | yes | Task decline |
| FIX | `/tasks/<int:task_id>/hot-proof` | POST | `record_hot_part_proof` | driver | - | driver | mutate | yes | Proof-before-complete needed |
| FIX | `/tasks/<int:task_id>/hot-proof-photo` | POST | `record_hot_part_photo` | driver | - | driver | mutate | yes | Upload validation needed |
| KEEP | `/truck-maintenance-history` | GET | `truck_maintenance_history` | driver | `truck_maintenance_history.html` | driver | read | yes | Driver truck history |
| KEEP | `/view_driver_log/<int:log_id>` | GET | `view_driver_log` | driver | `view_driver_log.html` | driver | read | yes | Driver stop view |
| MERGE | `/view_driving_log/<int:log_id>` | GET | `legacy_view_driving_log` | driver | - | login | read | no | Legacy redirect; add driver guard or delete |
| FIX | `/view_pretrip/<int:pretrip_id>` | GET,POST | `view_pretrip` | driver | `view_pretrip.html` | driver | mutate | yes | POST on view route; check finalized mutation behavior |

