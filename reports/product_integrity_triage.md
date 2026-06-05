# Product Integrity Audit Triage

Generated from `reports/product_integrity_report.md` on 2026-06-05.

## Current Static Result

- PASS: 1
- FAIL: 35
- NEEDS REVIEW: 443
- Total findings: 479

## Remaining FAIL Triage

### Form Submit Audit

The remaining form-submit FAILs are false positives from template snippets that stop before the visible submit control or from file-upload forms that use a label-wrapped file input and scripted submit.

Evidence:

- `templates/direct_messages.html:15` renders `dm_form.submit(...)`.
- `templates/profile.html:63` renders `profile_form.submit(...)`.
- `templates/reply_dm.html:19` renders `reply_form.submit(...)`.
- `templates/reply_message.html:20` renders `reply_form.submit(...)`.
- `templates/unified_dashboard.html:231` renders `form_create_task.submit(...)`.
- `templates/unified_dashboard.html:326` renders a visible `<button type="submit">Send DM</button>`.
- `templates/partials/_compact_route_map.html:42-91` file-proof forms use label controls with hidden file inputs and `onchange="if(this.files.length){this.form.submit();}"`.

### Finalization Mutation Guard Check

The remaining guard FAILs are pattern-matching false positives. The audited driver mutation paths are covered by shared route-lock helpers and regression tests.

Evidence:

- `app/blueprints/driver/routes.py:343-376` defines `_can_driver_change_same_day()` and `_guard_route_record_mutation()`, including finalized-route rejection.
- `app/blueprints/driver/routes.py:379-387` routes driver-log mutation checks through `_guard_driver_log_mutation()`.
- `app/blueprints/driver/routes.py:2973-2977` blocks PostTrip changes after route finalization.
- `app/blueprints/driver/routes.py:3345-3361` guards Plant Transfer edits and rechecks posted transfer dates before saving.
- `app/blueprints/driver/routes.py:3592-3600` blocks new driver-log creation on finalized routes.
- `app/blueprints/driver/routes.py:3779-3799`, `4022-4031`, `4157-4166`, `4344-4346`, and `4392-4394` guard edit, proof upload, depart, no-pickup, and pickup mutations.
- `app/blueprints/manager/routes.py:2168-2170` blocks manager proof deletion after route finalization.
- `tests/test_app_flows.py` covers finalized-route mutation blocks and Plant Transfer date-lock behavior.

### Silent Failure Check

`templates/manager_dashboard.html:1218` still flags because the scanner keys off `fetch(...)`, but the catch block now logs and renders visible user feedback.

Evidence:

- `templates/manager_dashboard.html:1221-1227` logs `Dispatch search suggestions failed` and renders `Suggestions unavailable / Search still filtered`.

## Real Findings Fixed In This Pass

- Dead placeholder navigation and fallback links now resolve to real routes.
- Upload size limit is configured with `MAX_UPLOAD_BYTES`.
- Damage packet wording now uses proof-record language instead of evidence-packet wording.
- Empty JavaScript catches now log safely.
- Finalized route/day records block active driver mutations while keeping print/view and missing-proof actions available.
- Printed route sheets include deviation reasons, full stop summary lines, route-completion status, and unsigned signature state.
