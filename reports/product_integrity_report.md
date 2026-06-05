# Product Integrity Audit — MoveDefense

**Status:** FAIL
**Profile:** movedefense
**Generated:** 2026-06-05T22:49:04.758356+00:00

## Summary

- PASS: 1
- FAIL: 35
- NEEDS REVIEW: 443
- Total findings: 479

## Findings

### 1. FAIL — form submit audit

**Location:** `templates/direct_messages.html:5`
**Selector:** `form`
**Expected:** Every form should have a visible submit path or script-managed submit with test coverage.
**Actual:** Form has no visible submit input/button in its body.
**Recommendation:** Add a submit control or document the scripted submission and add a test.

```text
{% extends "base.html" %}
{% block content %}
<div class="container">
  <h2 class="mt-3">Direct Messages</h2>
  <form method="POST" action="">
    {{ dm_form.hidden_tag() }}
    <div class="mb-3">
      {{ dm_form.receiver_id.label }}
      {{ dm_form.receiver_id(class="form-select") }}
    </div>
    <div class="mb-3">
      {{ d
```

### 2. FAIL — form submit audit

**Location:** `templates/manager_dashboard.html:450`
**Selector:** `form`
**Expected:** Every form should have a visible submit path or script-managed submit with test coverage.
**Actual:** Form has no visible submit input/button in its body.
**Recommendation:** Add a submit control or document the scripted submission and add a test.

```text
<div class="mctx-item right">
          <p>Truck ID</p>
          <p id="mgTruck">—</p>
        </div>
      </div>

      {# Task section (editable inline) #}
      <div id="mgTaskSec" style="display:none;">
        <form id="mgTaskForm" method="POST" style="display:contents;">
          <input type="hidden" name="csrf_token" id="mgCSRF">

          <div>
            <label class="flbl">Assign / Reassign Driver</label>
            <
```

### 3. FAIL — form submit audit

**Location:** `templates/profile.html:10`
**Selector:** `form`
**Expected:** Every form should have a visible submit path or script-managed submit with test coverage.
**Actual:** Form has no visible submit input/button in its body.
**Recommendation:** Add a submit control or document the scripted submission and add a test.

```text
agement' %}
<script>document.body.classList.add('md-shell');</script>
{% include 'partials/_md_shell.html' %}
{% endif %}
<div class="container fade-in" style="overflow-x: auto;">
  <h2 class="mt-4 mb-3">Profile</h2>

  <form method="POST" action="">
    {{ profile_form.hidden_tag() }}

    <!-- Username -->
    <div class="mb-3">
      {{ profile_form.username.label }}:
      {{ profile_form.username(class="form-control") }}
    </div>
```

### 4. FAIL — form submit audit

**Location:** `templates/reply_dm.html:8`
**Selector:** `form`
**Expected:** Every form should have a visible submit path or script-managed submit with test coverage.
**Actual:** Form has no visible submit input/button in its body.
**Recommendation:** Add a submit control or document the scripted submission and add a test.

```text
xtends "base.html" %}
{% block content %}
<div class="container">
  <h2 class="mt-3">Reply to Message</h2>
  <p><strong>Original from:</strong> {{ original_dm.sender.username }}</p>
  <p>{{ original_dm.content }}</p>

  <form method="POST" action="">
    {{ reply_form.hidden_tag() }}
    <!-- We can display the receiver (sender of original) read-only or hidden. -->
    <div class="mb-3">
      {{ reply_form.receiver_id.label }}
      {{
```

### 5. FAIL — form submit audit

**Location:** `templates/reply_message.html:10`
**Selector:** `form`
**Expected:** Every form should have a visible submit path or script-managed submit with test coverage.
**Actual:** Form has no visible submit input/button in its body.
**Recommendation:** Add a submit control or document the scripted submission and add a test.

```text
"mt-3">Reply to Message</h2>
  <p><strong>Original From:</strong> {{ original_dm.sender.username }}<br>
     {{ original_dm.content }}<br>
     <small class="text-muted">{{ original_dm.timestamp }}</small></p>
  <hr>

  <form method="POST" action="">
    {{ reply_form.hidden_tag() }}
    <div class="mb-3">
      {{ reply_form.receiver_id.label }}:
      {{ reply_form.receiver_id(class="form-select") }}
    </div>
    <div class="mb-3">
```

### 6. FAIL — form submit audit

**Location:** `templates/unified_dashboard.html:207`
**Selector:** `form`
**Expected:** Every form should have a visible submit path or script-managed submit with test coverage.
**Actual:** Form has no visible submit input/button in its body.
**Recommendation:** Add a submit control or document the scripted submission and add a test.

```text
rrent_user.role|capitalize }}</h2>
    <hr>

    <!-- If manager, show create_task_section -->
    {% if is_management %}
    <div id="create_task_section" class="my-4 p-3 border">
      <h4>Create a New Task</h4>
      <form method="POST">
        {{ form_create_task.hidden_tag() }}

        <div class="form-group">
          <label>Title</label>
          {{ form_create_task.title(class="form-control") }}
        </div>
        <div c
```

### 7. FAIL — form submit audit

**Location:** `templates/view_driver_log.html:485`
**Selector:** `form`
**Expected:** Every form should have a visible submit path or script-managed submit with test coverage.
**Actual:** Form has no visible submit input/button in its body.
**Recommendation:** Add a submit control or document the scripted submission and add a test.

```text
{% endif %}
            {% if not log.depart_time %}
              <a class="btn btn-success" href="{{ url_for('driver.depart_driver_log', log_id=log.id) }}">Record departure</a>
            {% endif %}
            <form action="{{ url_for('driver.record_driver_log_photo', log_id=log.id) }}" method="POST" enctype="multipart/form-data">
              <input type="hidden" name="source" value="proof">
              <input type="hidden
```

### 8. FAIL — form submit audit

**Location:** `templates/driver_task_detail.html:77`
**Selector:** `form`
**Expected:** Every form should have a visible submit path or script-managed submit with test coverage.
**Actual:** Form has no visible submit input/button in its body.
**Recommendation:** Add a submit control or document the scripted submission and add a test.

```text
ocomplete="off" inputmode="text" placeholder="Scan or enter part label">
      <button type="button" class="hot-photo-button" id="hotScanBtn">Scan Part Label</button>
    </div>
    <div class="hot-proof-actions">
      <form action="{{ url_for('driver.record_hot_part_photo', task_id=task.id) }}" method="POST" enctype="multipart/form-data">
        <input class="d-none" id="hotPartPhoto" name="photo" type="file" accept="image/*" capture
```

### 9. FAIL — form submit audit

**Location:** `templates/partials/_compact_route_map.html:42`
**Selector:** `form`
**Expected:** Every form should have a visible submit path or script-managed submit with test coverage.
**Actual:** Form has no visible submit input/button in its body.
**Recommendation:** Add a submit control or document the scripted submission and add a test.

```text
ss="route-detail-link" type="submit">Confirm correct destination</button>
        </form>
        <a class="route-detail-link" href="{{ url_for('driver.edit_driver_log', log_id=log_id) }}">Change destination</a>
        <form action="{{ url_for('driver.record_driver_log_photo', log_id=log_id) }}" method="POST" enctype="multipart/form-data">
          <input type="hidden" name="source" value="proof">
          <input type="hidden" name="
```

### 10. FAIL — form submit audit

**Location:** `templates/partials/_compact_route_map.html:49`
**Selector:** `form`
**Expected:** Every form should have a visible submit path or script-managed submit with test coverage.
**Actual:** Form has no visible submit input/button in its body.
**Recommendation:** Add a submit control or document the scripted submission and add a test.

```text
or('driver.request_manager_review', log_id=log_id) }}" method="POST"><button class="route-detail-link danger" type="submit">Send to manager review</button></form>
      {% elif primary_code == 'missing_proof' %}
        <form action="{{ url_for('driver.record_driver_log_photo', log_id=log_id) }}" method="POST" enctype="multipart/form-data">
          <input type="hidden" name="source" value="proof">
          <input type="hidden" name="
```

### 11. FAIL — form submit audit

**Location:** `templates/partials/_compact_route_map.html:66`
**Selector:** `form`
**Expected:** Every form should have a visible submit path or script-managed submit with test coverage.
**Actual:** Form has no visible submit input/button in its body.
**Recommendation:** Add a submit control or document the scripted submission and add a test.

```text
ger review</button></form>
      {% elif primary_code == 'needs_departure' %}
        <a class="route-detail-link" href="{{ depart_url or url_for('driver.view_driver_log', log_id=log_id) }}">Record departure</a>
        <form action="{{ url_for('driver.record_driver_log_photo', log_id=log_id) }}" method="POST" enctype="multipart/form-data">
          <input type="hidden" name="source" value="proof">
          <input type="hidden" name="
```

### 12. FAIL — form submit audit

**Location:** `templates/partials/_compact_route_map.html:75`
**Selector:** `form`
**Expected:** Every form should have a visible submit path or script-managed submit with test coverage.
**Actual:** Form has no visible submit input/button in its body.
**Recommendation:** Add a submit control or document the scripted submission and add a test.

```text
" method="POST"><button class="route-detail-link" type="submit">Confirm no pickup</button></form>
        <a class="route-detail-link" href="{{ url_for('driver.edit_driver_log', log_id=log_id) }}">Add reason</a>
        <form action="{{ url_for('driver.record_driver_log_photo', log_id=log_id) }}" method="POST" enctype="multipart/form-data">
          <input type="hidden" name="source" value="proof">
          <input type="hidden" name="
```

### 13. FAIL — form submit audit

**Location:** `templates/partials/_compact_route_map.html:88`
**Selector:** `form`
**Expected:** Every form should have a visible submit path or script-managed submit with test coverage.
**Actual:** Form has no visible submit input/button in its body.
**Recommendation:** Add a submit control or document the scripted submission and add a test.

```text
}">
          <input class="route-detail-closeout" name="reason" placeholder="Closeout reason" required>
          <button class="route-detail-link" type="submit">Close issue to continue</button>
        </form>
        <form action="{{ url_for('driver.record_driver_log_photo', log_id=log_id) }}" method="POST" enctype="multipart/form-data">
          <input type="hidden" name="source" value="proof">
          <input type="hidden" name="
```

### 14. FAIL — form submit audit

**Location:** `templates/partials/_desktop_ops_workspace.html:128`
**Selector:** `form`
**Expected:** Every form should have a visible submit path or script-managed submit with test coverage.
**Actual:** Form has no visible submit input/button in its body.
**Recommendation:** Add a submit control or document the scripted submission and add a test.

```text
owner_id='', primary=true, allowed=true) -%}
  {% if log_id and allowed %}
    <details class="desk-attach-doc">
      <summary class="desk-action-link{% if primary %} primary{% endif %}">Attach Document</summary>
      <form class="desk-attach-doc-panel" method="POST" action="{{ url_for('driver.record_driver_log_photo', log_id=log_id) }}" enctype="multipart/form-data">
        <input type="hidden" name="source" value="route_workspace">
```

### 15. FAIL — finalization mutation guard check

**Location:** `app/blueprints/driver/routes.py:3029`
**Expected:** Mutating routes must check finalized/submitted/locked state before changing route records or evidence.
**Actual:** Potential mutating route/function found without an obvious finalization guard.
**Recommendation:** Add server-side finalized-route guard and regression tests for add/edit/upload/delete/depart after finalization.

```text
@bp.route("/view_pretrip/<int:pretrip_id>", methods=["GET", "POST"])
@login_required
def view_pretrip(pretrip_id):
    pt = _active_pretrips_query().filter_by(id=pretrip_id).first_or_404()
    if current_user.role == "driver":
        if not _driver_can_view_inspection_pretrip(pt):
            flash("Not authorized to view that PreTrip.", "danger")
            return redirect(url_for("driver.list_pretrips"))
        return redirect(url_for("driver.pretrip_printable", pretrip_id=pt.id))
    return render_template(
        "view_pretrip.html",
        pretrip=pt,
        readonly=True,
        today_local_date=_today_local_date(),
        pretrip_damage_reports=_pretrip_damage_reports(pt),
        document_meta=_pretrip_document_meta(pt),
    )
```

### 16. FAIL — finalization mutation guard check

**Location:** `app/blueprints/driver/routes.py:3258`
**Expected:** Mutating routes must check finalized/submitted/locked state before changing route records or evidence.
**Actual:** Potential mutating route/function found without an obvious finalization guard.
**Recommendation:** Add server-side finalized-route guard and regression tests for add/edit/upload/delete/depart after finalization.

```text
@bp.route("/plant_transfers/new", methods=["GET", "POST"])
@login_required
def new_plant_transfer():
    form = PlantTransferForm()
    if request.method == "GET" and not form.driver_name.data:
        form.driver_name.data = current_user.display_name
    lines = _plant_transfer_form_lines()
    if request.method == "GET":
        guard = _guard_route_record_mutation(
            current_user.id,
            _today_local_date(),
            "Plant Transfer",
            "create",
            next_url=url_for("driver.plant_transfers"),
        )
        if guard:
            return guard
    elif request.method == "POST":
        guard = _guard_route_record_mutation(
            current_user.id,
            form.transfer_date.data or _today_local_date(),
            "Plant Transfer",
            "create",
            next_url=url_for("driver.plant_transfers"),
        )
        if guard:
            return guard
    if form.validate_on_submit():
        if not any(_plant_transfer_line
```

### 17. FAIL — finalization mutation guard check

**Location:** `app/blueprints/driver/routes.py:3333`
**Expected:** Mutating routes must check finalized/submitted/locked state before changing route records or evidence.
**Actual:** Potential mutating route/function found without an obvious finalization guard.
**Recommendation:** Add server-side finalized-route guard and regression tests for add/edit/upload/delete/depart after finalization.

```text
@bp.route("/plant_transfers/<int:transfer_id>/edit", methods=["GET", "POST"])
@login_required
def edit_plant_transfer(transfer_id):
    transfer = _get_plant_transfer_or_redirect(transfer_id)
    if transfer is None:
        return redirect(url_for("driver.plant_transfers"))
    if current_user.role == "management":
        flash("Managers have read-only access to driver Plant Transfers.", "warning")
        return redirect(url_for("driver.view_plant_transfer", transfer_id=transfer.id))
    form = PlantTransferForm(obj=transfer)
    guard = _guard_route_record_mutation(
        transfer.user_id,
        transfer.transfer_date,
        "Plant Transfer",
        "update",
        next_url=url_for("driver.view_plant_transfer", transfer_id=transfer.id),
    )
    if guard:
        return guard
    if request.method == "GET":
        form.transfer_time.data = _format_display_time(transfer.transfer_time)
    lines = _plant_transfer_form_lines(transfer)
    if form.validate_on_submit():
```

### 18. FAIL — finalization mutation guard check

**Location:** `app/blueprints/driver/routes.py:3404`
**Expected:** Mutating routes must check finalized/submitted/locked state before changing route records or evidence.
**Actual:** Potential mutating route/function found without an obvious finalization guard.
**Recommendation:** Add server-side finalized-route guard and regression tests for add/edit/upload/delete/depart after finalization.

```text
@bp.route("/plant_transfers/<int:transfer_id>/delete", methods=["POST"])
@login_required
def delete_plant_transfer(transfer_id):
    transfer = _active_plant_transfers_query().filter_by(id=transfer_id).first_or_404()
    if not _can_driver_change_same_day(
        transfer.user_id, transfer.transfer_date, "Plant Transfer", "delete"
    ):
        return redirect(url_for("driver.plant_transfers"))

    transfer_number = transfer.transfer_number or transfer.id
    route = f"{transfer.ship_from} to {transfer.ship_to}"
    _soft_delete_record(transfer)
    record_activity(
        user_id=current_user.id,
        category="transfer",
        action="deleted",
        title="Plant Transfer deleted",
        details=f"{transfer_number}: {route}.",
        target_type="plant_transfer",
        target_id=transfer_id,
    )
    db.session.commit()
    flash("Plant Transfer deleted.", "success")
    return redirect(url_for("driver.plant_transfers"))
```

### 19. FAIL — finalization mutation guard check

**Location:** `app/blueprints/driver/routes.py:3485`
**Expected:** Mutating routes must check finalized/submitted/locked state before changing route records or evidence.
**Actual:** Potential mutating route/function found without an obvious finalization guard.
**Recommendation:** Add server-side finalized-route guard and regression tests for add/edit/upload/delete/depart after finalization.

```text
@bp.route("/plant_transfers/<int:transfer_id>/mark_printed", methods=["POST"])
@login_required
def mark_plant_transfer_printed(transfer_id):
    transfer = _get_plant_transfer_or_redirect(transfer_id)
    if transfer is None:
        return jsonify({"ok": False, "error": "not_authorized"}), 403
    record_activity(
        user_id=current_user.id,
        category="print",
        action="plant_transfer_printed",
        title="Plant Transfer printed",
        details=(
            f"{transfer.ship_from} to {transfer.ship_to}; "
            f"copy: {request.args.get('copy', 'selected')}."
        ),
        target_type="plant_transfer",
        target_id=transfer.id,
    )
    return jsonify({"ok": True})
```

### 20. FAIL — finalization mutation guard check

**Location:** `app/blueprints/driver/routes.py:3577`
**Expected:** Mutating routes must check finalized/submitted/locked state before changing route records or evidence.
**Actual:** Potential mutating route/function found without an obvious finalization guard.
**Recommendation:** Add server-side finalized-route guard and regression tests for add/edit/upload/delete/depart after finalization.

```text
@bp.route("/new_driving_log", methods=["GET", "POST"])
@login_required
@_driver_route_guard("driver.mobile_dashboard", "the driver log page")
def new_driving_log():
    form = DriverLogForm()
    pending_ryder_event = _open_ryder_event(current_user.id)
    local_tz = pytz.timezone("America/Detroit")
    now_local = datetime.now(local_tz)
    open_shift = _open_shift_for_driver(current_user.id)
    local_date = _active_route_date_for_driver(current_user.id, now_local.date(), open_shift=open_shift)
    current_load = _current_driver_load(current_user.id, route_date=local_date)
    current_load_value = current_load["value"] or "Empty"
    current_secondary_value = current_load.get("secondary_value") or ""
    guard = _guard_route_record_mutation(
        current_user.id,
        local_date,
        "driver log",
        "create",
        next_url=_driver_logs_url_for_date(local_date),
    )
    if guard:
        return guard

    if form.validate_on_submit():
        if pending_ryder_ev
```

### 21. FAIL — finalization mutation guard check

**Location:** `app/blueprints/driver/routes.py:3770`
**Expected:** Mutating routes must check finalized/submitted/locked state before changing route records or evidence.
**Actual:** Potential mutating route/function found without an obvious finalization guard.
**Recommendation:** Add server-side finalized-route guard and regression tests for add/edit/upload/delete/depart after finalization.

```text
@bp.route("/edit_driver_log/<int:log_id>", methods=["GET", "POST"])
@login_required
def edit_driver_log(log_id):
    log = _active_driver_logs_query().filter_by(id=log_id).first_or_404()
    if current_user.role == "driver" and log.driver_id != current_user.id:
        flash("Not authorized to edit someone else's log!", "danger")
        return redirect(url_for("driver.driver_logs"))
    guard = _guard_driver_log_mutation(log, "edit", next_url=_driver_logs_url_for_date(log.date))
    if guard:
        return guard

    form = DriverLogForm(obj=log)
    ensure_legacy_plant_choice(form.plant_name, log.plant_name)
    if request.method == "GET":
        form.arrive_time.data = _arrival_utc_to_local_hhmm(log.arrive_time)
        issue_code, issue_notes = _split_truck_issue_text(truck_issue_reason(log) or route_problem_reason(log))
        form.truck_issue.data = issue_code
        form.truck_issue_notes.data = issue_notes
        form.departure_destination.data = destination_from_load(lo
```

### 22. FAIL — finalization mutation guard check

**Location:** `app/blueprints/driver/routes.py:3870`
**Expected:** Mutating routes must check finalized/submitted/locked state before changing route records or evidence.
**Actual:** Potential mutating route/function found without an obvious finalization guard.
**Recommendation:** Add server-side finalized-route guard and regression tests for add/edit/upload/delete/depart after finalization.

```text
@bp.route("/edit_driving_log/<int:log_id>", methods=["GET", "POST"], strict_slashes=False)
@login_required
def legacy_edit_driving_log(log_id):
    return redirect(url_for("driver.edit_driver_log", log_id=log_id), code=307 if request.method == "POST" else 302)
```

### 23. FAIL — finalization mutation guard check

**Location:** `app/blueprints/driver/routes.py:3882`
**Expected:** Mutating routes must check finalized/submitted/locked state before changing route records or evidence.
**Actual:** Potential mutating route/function found without an obvious finalization guard.
**Recommendation:** Add server-side finalized-route guard and regression tests for add/edit/upload/delete/depart after finalization.

```text
@bp.route("/depart_driver_log/<int:log_id>", methods=["GET", "POST"], strict_slashes=False)
@login_required
def legacy_depart_driver_log(log_id):
    return redirect(url_for("driver.depart_driver_log", log_id=log_id), code=307 if request.method == "POST" else 302)
```

### 24. FAIL — finalization mutation guard check

**Location:** `app/blueprints/driver/routes.py:3888`
**Expected:** Mutating routes must check finalized/submitted/locked state before changing route records or evidence.
**Actual:** Potential mutating route/function found without an obvious finalization guard.
**Recommendation:** Add server-side finalized-route guard and regression tests for add/edit/upload/delete/depart after finalization.

```text
@bp.route("/pickup_driver_log/<int:log_id>", methods=["GET", "POST"], strict_slashes=False)
@login_required
def legacy_pickup_driver_log(log_id):
    return redirect(url_for("driver.depart_driver_log", log_id=log_id), code=307 if request.method == "POST" else 302)
```

### 25. FAIL — finalization mutation guard check

**Location:** `app/blueprints/driver/routes.py:3900`
**Expected:** Mutating routes must check finalized/submitted/locked state before changing route records or evidence.
**Actual:** Potential mutating route/function found without an obvious finalization guard.
**Recommendation:** Add server-side finalized-route guard and regression tests for add/edit/upload/delete/depart after finalization.

```text
@bp.route("/driver_logs/<int:log_id>/delete", methods=["POST"], strict_slashes=False)
@login_required
def delete_driver_log(log_id):
    log = _active_driver_logs_query().filter_by(id=log_id).first_or_404()
    if not _can_driver_change_same_day(log.driver_id, log.date, "driver log", "delete"):
        return redirect(url_for("driver.driver_logs"))

    details = f"{log.plant_name} / {log.load_size} load for {log.date}."
    _soft_delete_record(log)
    record_activity(
        user_id=current_user.id,
        category="log",
        action="deleted",
        title="Driver log deleted",
        details=details,
        target_type="driver_log",
        target_id=log_id,
    )
    db.session.commit()
    _emit_driver_log_updated(log, "deleted")
    flash("Driver log deleted.", "success")
    return redirect(url_for("driver.driver_logs"))
```

### 26. FAIL — finalization mutation guard check

**Location:** `app/blueprints/driver/routes.py:3982`
**Expected:** Mutating routes must check finalized/submitted/locked state before changing route records or evidence.
**Actual:** Potential mutating route/function found without an obvious finalization guard.
**Recommendation:** Add server-side finalized-route guard and regression tests for add/edit/upload/delete/depart after finalization.

```text
@bp.route("/driver_logs/photos/<int:photo_id>/delete", methods=["POST"], strict_slashes=False)
@login_required
def delete_driver_log_photo(photo_id):
    photo = DriverLogPhoto.query.get_or_404(photo_id)
    log = photo.log
    if not log or log.driver_id != current_user.id:
        abort(403)
    guard = _guard_driver_log_mutation(
        log,
        "delete proof from",
        next_url=request.form.get("next") or url_for("driver.edit_driver_log", log_id=log.id),
    )
    if guard:
        return guard
    photo_label = photo.original_filename or photo.filename
    note = photo.note
    _delete_driver_log_photo_file(photo)
    record_activity(
        user_id=current_user.id,
        category="log_photo",
        action="deleted",
        title="Stop photo proof deleted",
        details=f"Deleted stop photo {photo_label}. Reason was: {note or 'No reason recorded'}",
        target_type="driver_log",
        target_id=log.id,
        commit=False,
    )
    db.session.delete(pho
```

### 27. FAIL — finalization mutation guard check

**Location:** `app/blueprints/driver/routes.py:4015`
**Expected:** Mutating routes must check finalized/submitted/locked state before changing route records or evidence.
**Actual:** Potential mutating route/function found without an obvious finalization guard.
**Recommendation:** Add server-side finalized-route guard and regression tests for add/edit/upload/delete/depart after finalization.

```text
@bp.route("/driver_logs/<int:log_id>/photos", methods=["POST"], strict_slashes=False)
@login_required
def record_driver_log_photo(log_id):
    log = _active_driver_logs_query().filter_by(id=log_id).first_or_404()
    next_url = request.form.get("next") or url_for("driver.edit_driver_log", log_id=log.id)
    guard = _guard_driver_log_mutation(
        log,
        "attach a document to",
        wants_json=_photo_upload_wants_json(),
        next_url=next_url,
    )
    if guard:
        if not _photo_upload_wants_json():
            flash("UPLOAD FAILED\nNot authorized to attach a document to this stop.", "danger")
        return guard

    document_type = (request.form.get("document_type") or "").strip()
    capture_source = (request.form.get("source") or "gallery").strip() or "gallery"
    owner_type = (request.form.get("owner_type") or "").strip()
    owner_id = (request.form.get("owner_id") or "").strip()
    upload_source = f"{document_type}_{capture_source}" if document_type el
```

### 28. FAIL — finalization mutation guard check

**Location:** `app/blueprints/driver/routes.py:4121`
**Expected:** Mutating routes must check finalized/submitted/locked state before changing route records or evidence.
**Actual:** Potential mutating route/function found without an obvious finalization guard.
**Recommendation:** Add server-side finalized-route guard and regression tests for add/edit/upload/delete/depart after finalization.

```text
@bp.route("/driver_logs/<int:log_id>/depart", methods=["GET", "POST"], strict_slashes=False)
@login_required
@_driver_route_guard("driver.driver_logs", "that departure page", "Driver Logs")
def depart_driver_log(log_id):
    log = _active_driver_logs_query().filter_by(id=log_id).first_or_404()
    quick_depart = (
        request.form.get("next") == "mobile"
        or request.args.get("next") == "mobile"
        or request.form.get("source") == "live_flow"
    )
    quick_fetch = quick_depart and request.headers.get("X-Requested-With") == "fetch"
```

### 29. FAIL — finalization mutation guard check

**Location:** `app/blueprints/driver/routes.py:4336`
**Expected:** Mutating routes must check finalized/submitted/locked state before changing route records or evidence.
**Actual:** Potential mutating route/function found without an obvious finalization guard.
**Recommendation:** Add server-side finalized-route guard and regression tests for add/edit/upload/delete/depart after finalization.

```text
@bp.route("/driver_logs/<int:log_id>/no_pickup", methods=["POST"], strict_slashes=False)
@login_required
def no_pickup_driver_log(log_id):
    log = _active_driver_logs_query().filter_by(id=log_id).first_or_404()
    guard = _guard_driver_log_mutation(log, "update")
    if guard:
        return guard
    if log.depart_time:
        flash("That log already has a departure time.", "warning")
        return redirect(url_for("driver.driver_logs"))

    local_tz = pytz.timezone("America/Detroit")
    now_local = datetime.now(local_tz)
    depart_time = now_local.strftime("%H:%M")
    timing_errors = _route_timing_errors(log.driver_id, log.date, log.plant_name, _arrival_hhmm_for_log(log), depart_time, exclude_log_id=log.id, check_previous=False)
    if timing_errors:
        flash(timing_errors[0], "danger")
        return redirect(url_for("driver.driver_logs"))
    log.no_pickup = True
    log.depart_load_size = "Empty"
    log.depart_time = depart_time
    log.dock_wait_minutes = _auto
```

### 30. FAIL — finalization mutation guard check

**Location:** `app/blueprints/driver/routes.py:4383`
**Expected:** Mutating routes must check finalized/submitted/locked state before changing route records or evidence.
**Actual:** Potential mutating route/function found without an obvious finalization guard.
**Recommendation:** Add server-side finalized-route guard and regression tests for add/edit/upload/delete/depart after finalization.

```text
@bp.route("/driver_logs/<int:log_id>/pickup", methods=["GET", "POST"], strict_slashes=False)
@login_required
def pickup_driver_log(log_id):
    log = _active_driver_logs_query().filter_by(id=log_id).first_or_404()
    if current_user.role == "driver" and log.driver_id != current_user.id:
        flash("Not authorized to pick up from someone else's log!", "danger")
        return redirect(url_for("driver.driver_logs"))
    guard = _guard_driver_log_mutation(log, "pick up from")
    if guard:
        return guard
    if log.depart_time:
        flash("That log already has a departure time.", "warning")
        return redirect(url_for("driver.driver_logs"))

    form = DriverLogForm()
    _prefill_log_form_from_task(form)
    if form.validate_on_submit():
        if not form.plant_name.data:
            flash("Please select where the load is going.", "danger")
            return render_template("pickup_driver_log.html", form=form, log=log)

        now_local = datetime.now(pytz.timezone
```

### 31. FAIL — finalization mutation guard check

**Location:** `app/blueprints/manager/routes.py:1824`
**Expected:** Mutating routes must check finalized/submitted/locked state before changing route records or evidence.
**Actual:** Potential mutating route/function found without an obvious finalization guard.
**Recommendation:** Add server-side finalized-route guard and regression tests for add/edit/upload/delete/depart after finalization.

```text
@bp.route("/review", methods=["GET", "POST"])
def review_dashboard():
    form = OperationalFollowUpForm()
    if form.validate_on_submit():
        followup = OperationalFollowUp(
            created_by_id=current_user.id,
            kind=form.kind.data,
            plant_name=form.plant_name.data or None,
            details=form.details.data,
        )
        db.session.add(followup)
        db.session.commit()
        record_activity(
            user_id=current_user.id,
            category="followup",
            action="created",
            title="Operational follow-up added",
            details=f"{followup.kind.replace('_', ' ').title()}: {followup.details}",
            target_type="followup",
            target_id=followup.id,
        )
        flash("Follow-up added.", "success")
        return redirect(url_for("manager.review_dashboard"))

    exceptions = _with_exception_urls(_active_exception_items())
    metrics = {
        "active_count": len(exceptions),
```

### 32. FAIL — finalization mutation guard check

**Location:** `app/blueprints/manager/routes.py:2194`
**Expected:** Mutating routes must check finalized/submitted/locked state before changing route records or evidence.
**Actual:** Potential mutating route/function found without an obvious finalization guard.
**Recommendation:** Add server-side finalized-route guard and regression tests for add/edit/upload/delete/depart after finalization.

```text
@bp.route("/damage-reports/<int:report_id>/delete", methods=["POST"])
def delete_damage_report(report_id):
    report = DamageReport.query.get_or_404(report_id)
    before = model_snapshot(
        report,
        [
            "reported_by_id",
            "task_id",
            "driver_log_id",
            "plant_transfer_id",
            "truck_number",
            "trailer_number",
            "plant_name",
            "damage_time",
            "stage",
            "move_reference",
            "description",
            "status",
            "created_at",
            "resolved_at",
        ],
    )
    before["photos"] = [photo.filename for photo in report.photos]
    report.status = "closed"
    report.resolved_at = datetime.utcnow()
    after = model_snapshot(
        report,
        [
            "status",
            "resolved_at",
        ],
    )
    after["photos_preserved"] = [photo.filename for photo in report.photos]
    record_audit_event(
        user_id=current_use
```

### 33. FAIL — finalization mutation guard check

**Location:** `app/blueprints/manager/routes.py:2333`
**Expected:** Mutating routes must check finalized/submitted/locked state before changing route records or evidence.
**Actual:** Potential mutating route/function found without an obvious finalization guard.
**Recommendation:** Add server-side finalized-route guard and regression tests for add/edit/upload/delete/depart after finalization.

```text
@bp.route("/dashboard", methods=["GET", "POST"])
def manager_dashboard():
    create_task_form = TaskForm()
    drivers = _populate_task_driver_choices(create_task_form)
    today = date.today()
    division_filter = request.args.get("division", "All")
    if division_filter not in {"All", "Plastics", "Trim"}:
        division_filter = "All"
    selected_driver_id = request.args.get("driver_id", type=int)
    selected_plant = (request.args.get("plant") or "").strip() or None
    focus_panel = request.args.get("focus", "jobs")
    if focus_panel not in {"jobs", "routes"}:
        focus_panel = "jobs"
    focus_target = request.args.get("target", "")
    if focus_target not in {"attention", "capture", "jobs", "routes", "reviews", "cases"}:
        focus_target = ""

    day_start = datetime.combine(today, datetime.min.time())
    uncompleted_tasks = (
        Task.query.filter(or_(Task.status != "completed", Task.completed_at >= day_start))
        .order_by(Task.created_at.desc())
```

### 34. FAIL — finalization mutation guard check

**Location:** `app/blueprints/manager/routes.py:2750`
**Expected:** Mutating routes must check finalized/submitted/locked state before changing route records or evidence.
**Actual:** Potential mutating route/function found without an obvious finalization guard.
**Recommendation:** Add server-side finalized-route guard and regression tests for add/edit/upload/delete/depart after finalization.

```text
@bp.route("/plant-transfers/<int:transfer_id>/mark_printed", methods=["POST"])
def mark_plant_transfer_printed(transfer_id):
    transfer = _active_plant_transfers_query().filter_by(id=transfer_id).first_or_404()
    record_activity(
        user_id=current_user.id,
        category="print",
        action="manager_plant_transfer_printed",
        title="Manager Plant Transfer printed",
        details=(
            f"{transfer.ship_from} to {transfer.ship_to}; "
            f"copy: {request.args.get('copy', 'selected')}."
        ),
        target_type="plant_transfer",
        target_id=transfer.id,
    )
    return jsonify({"ok": True})
```

### 35. FAIL — silent failure check

**Location:** `templates/manager_dashboard.html:1218`
**Expected:** Failures should show visible user feedback and log safely server-side.
**Actual:** fetch call may lack error handling.
**Recommendation:** Add explicit error handling, logging, and flash/toast/UI error messages.

```text
> {
  const q = srch.value.trim();
  applyDispatchSearch(q);
  clearTimeout(searchTimer);
  if (q.length < 2) { renderSuggestions([]); return; }
  searchTimer = setTimeout(async () => {
    try {
      const res = await fetch(`{{ url_for('manager.search_suggest') }}?q=${encodeURIComponent(q)}`);
      const data = await res.json();
      renderSuggestions(data.results || []);
    } catch (err) {
      if (window.console && console.warn)
```

### 36. NEEDS REVIEW — button route audit

**Location:** `templates/end_of_day_summary.html:189`
**Selector:** `button:has-text('Clear')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: Clear
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
block; touch-action:none;">
      <canvas id="sigCanvas" width="480" height="160" tabindex="0"
              style="display:block; background:#fff; cursor:crosshair; border-radius:4px;"></canvas>
    </div>
    <br>
    <button type="button" class="btn btn-outline-secondary btn-sm me-2" id="sigClear">Clear</button>
    <button type="submit" class="btn btn-success" id="sigSubmit">Sign &amp; Submit</button>
    </section>
  </form>
</div>
```

### 37. NEEDS REVIEW — button route audit

**Location:** `templates/manager_dashboard.html:1202`
**Selector:** `button:has-text('${term} ${category} · ${Number(item.frequency || 0)}')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: ${term} ${category} · ${Number(item.frequency || 0)}
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
.innerHTML = '';
    return;
  }
  suggestions.innerHTML = results.map(item => {
    const term = escapeHtml(item.term);
    const category = escapeHtml(String(item.category || '').replace('_', ' '));
    return `
      <button type="button" class="suggestion-item" data-term="${term}">
        <span class="suggestion-term">${term}</span>
        <span class="suggestion-meta">${category} · ${Number(item.frequency || 0)}</span>
      </bu
```

### 38. NEEDS REVIEW — button route audit

**Location:** `templates/driver_task_detail.html:74`
**Selector:** `button:has-text('Scan Part Label')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: Scan Part Label
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
us warn">{{ hot_part_proof.open_exception }}</strong>{% endif %}
    </div>
    <div class="hot-scan-row">
      <input id="hotScanValue" autocomplete="off" inputmode="text" placeholder="Scan or enter part label">
      <button type="button" class="hot-photo-button" id="hotScanBtn">Scan Part Label</button>
    </div>
    <div class="hot-proof-actions">
      <form action="{{ url_for('driver.record_hot_part_photo', task_id=task.id) }}" m
```

### 39. NEEDS REVIEW — button route audit

**Location:** `templates/driver_task_detail.html:81`
**Selector:** `button:has-text('Picked Up')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: Picked Up
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
mage/*" capture="environment" onchange="this.form.submit()">
        <button type="button" class="hot-photo-button w-100" onclick="document.getElementById('hotPartPhoto').click()">Take Photo</button>
      </form>
      <button type="button" data-hot-event="picked_up">Picked Up</button>
      <button type="button" data-hot-event="dropped_off">Dropped Off</button>
      <button type="button" data-hot-event="cant_find_part">Can't Find Par
```

### 40. NEEDS REVIEW — button route audit

**Location:** `templates/driver_task_detail.html:82`
**Selector:** `button:has-text('Dropped Off')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: Dropped Off
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
on type="button" class="hot-photo-button w-100" onclick="document.getElementById('hotPartPhoto').click()">Take Photo</button>
      </form>
      <button type="button" data-hot-event="picked_up">Picked Up</button>
      <button type="button" data-hot-event="dropped_off">Dropped Off</button>
      <button type="button" data-hot-event="cant_find_part">Can't Find Part</button>
      <button type="button" data-hot-event="wrong_part">Wrong P
```

### 41. NEEDS REVIEW — button route audit

**Location:** `templates/driver_task_detail.html:83`
**Selector:** `button:has-text("Can't Find Part")`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: Can't Find Part
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
Id('hotPartPhoto').click()">Take Photo</button>
      </form>
      <button type="button" data-hot-event="picked_up">Picked Up</button>
      <button type="button" data-hot-event="dropped_off">Dropped Off</button>
      <button type="button" data-hot-event="cant_find_part">Can't Find Part</button>
      <button type="button" data-hot-event="wrong_part">Wrong Part</button>
      <button type="button" data-hot-event="delay_reported">Repor
```

### 42. NEEDS REVIEW — button route audit

**Location:** `templates/driver_task_detail.html:84`
**Selector:** `button:has-text('Wrong Part')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: Wrong Part
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
ton" data-hot-event="picked_up">Picked Up</button>
      <button type="button" data-hot-event="dropped_off">Dropped Off</button>
      <button type="button" data-hot-event="cant_find_part">Can't Find Part</button>
      <button type="button" data-hot-event="wrong_part">Wrong Part</button>
      <button type="button" data-hot-event="delay_reported">Report Delay</button>
    </div>
    <p class="hot-proof-status" id="hotProofStatus">{{ ho
```

### 43. NEEDS REVIEW — button route audit

**Location:** `templates/driver_task_detail.html:85`
**Selector:** `button:has-text('Report Delay')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: Report Delay
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
n" data-hot-event="dropped_off">Dropped Off</button>
      <button type="button" data-hot-event="cant_find_part">Can't Find Part</button>
      <button type="button" data-hot-event="wrong_part">Wrong Part</button>
      <button type="button" data-hot-event="delay_reported">Report Delay</button>
    </div>
    <p class="hot-proof-status" id="hotProofStatus">{{ hot_part_proof.proof_sentence }}</p>
  </section>

  {% endif %}

  <div class
```

### 44. NEEDS REVIEW — button route audit

**Location:** `templates/plant_transfer_form.html:106`
**Selector:** `button:has-text('Add Part Line')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: Add Part Line
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
<div class="transfer-line-toolbar">
      <div>
        <p class="md-section-label mb-0">PART LINES</p>
        <div class="transfer-line-count">Part Number · Quantity · Skids · Remarks · LP IDs</div>
      </div>
      <button type="button" class="btn btn-outline-primary" data-add-transfer-line>Add Part Line</button>
    </div>

    <div class="transfer-line-list" data-transfer-line-list>
      {% for line in lines %}
        {% set li
```

### 45. NEEDS REVIEW — button route audit

**Location:** `templates/plant_transfer_form.html:139`
**Selector:** `button:has-text('Scan LP IDs')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: Scan LP IDs
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
label>
              <input id="remarks{{ line.index }}" name="remarks_{{ line.index }}" class="form-control" value="{{ line.remarks }}">
            </div>
            <div class="transfer-proof-actions">
              <button type="button" class="btn btn-outline-primary" data-focus-lp="lpIds{{ line.index }}">Scan LP IDs</button>
              <button type="button" class="btn btn-outline-secondary" data-focus-lp="remarks{{ line.index }
```

### 46. NEEDS REVIEW — button route audit

**Location:** `templates/plant_transfer_form.html:140`
**Selector:** `button:has-text('Attach proof note')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: Attach proof note
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
marks }}">
            </div>
            <div class="transfer-proof-actions">
              <button type="button" class="btn btn-outline-primary" data-focus-lp="lpIds{{ line.index }}">Scan LP IDs</button>
              <button type="button" class="btn btn-outline-secondary" data-focus-lp="remarks{{ line.index }}">Attach proof note</button>
            </div>
          </div>
        </details>
      {% endfor %}
    </div>

    <div cl
```

### 47. NEEDS REVIEW — button route audit

**Location:** `templates/_driver_log_photo_upload.html:41`
**Selector:** `button:has-text('Upload From Gallery')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: Upload From Gallery
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
rol mb-2" id="stopPhotoNote-{{ photo_source_prefix }}" rows="2" maxlength="500" data-stop-photo-note placeholder="Only add detail if something needs manager attention."></textarea>
  <div class="stop-photo-actions">
    <button type="button" data-stop-photo-trigger data-source="{{ photo_source_prefix }}_gallery">Upload From Gallery</button>
    <button class="secondary" type="button" data-stop-photo-trigger data-source="{{ photo_source_
```

### 48. NEEDS REVIEW — button route audit

**Location:** `templates/_driver_log_photo_upload.html:42`
**Selector:** `button:has-text('Take New Photo')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: Take New Photo
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
il if something needs manager attention."></textarea>
  <div class="stop-photo-actions">
    <button type="button" data-stop-photo-trigger data-source="{{ photo_source_prefix }}_gallery">Upload From Gallery</button>
    <button class="secondary" type="button" data-stop-photo-trigger data-source="{{ photo_source_prefix }}_camera">Take New Photo</button>
    <input class="d-none" type="file" accept="image/*" data-stop-photo-input="{{ phot
```

### 49. NEEDS REVIEW — button route audit

**Location:** `templates/depart_driver_log.html:105`
**Selector:** `button:has-text('Scan Unloaded / Dropped Cargo')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: Scan Unloaded / Dropped Cargo
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
ation</h3>
      <p class="text-muted small mb-2">Scan cargo coming off this stop or leaving with you. Unknown parts are saved for manager confirmation instead of being lost.</p>
      <div class="scan-actions">
        <button type="button" data-scan-context="drop_scan">Scan Unloaded / Dropped Cargo</button>
        <button type="button" data-scan-context="departure_scan">Scan Loaded / Departing Cargo</button>
      </div>
      <div c
```

### 50. NEEDS REVIEW — button route audit

**Location:** `templates/depart_driver_log.html:106`
**Selector:** `button:has-text('Scan Loaded / Departing Cargo')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: Scan Loaded / Departing Cargo
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
ou. Unknown parts are saved for manager confirmation instead of being lost.</p>
      <div class="scan-actions">
        <button type="button" data-scan-context="drop_scan">Scan Unloaded / Dropped Cargo</button>
        <button type="button" data-scan-context="departure_scan">Scan Loaded / Departing Cargo</button>
      </div>
      <div class="input-group input-group-sm" style="max-width:520px;">
        <input class="form-control" id=
```

### 51. NEEDS REVIEW — button route audit

**Location:** `templates/depart_driver_log.html:110`
**Selector:** `button:has-text('Save Manual Scan')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: Save Manual Scan
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
ton>
      </div>
      <div class="input-group input-group-sm" style="max-width:520px;">
        <input class="form-control" id="manualScanValue" autocomplete="off" placeholder="Manual barcode / part fallback">
        <button class="btn btn-outline-secondary" type="button" id="manualScanBtn">Save Manual Scan</button>
      </div>
      <div class="scanner-stage" id="scannerStage">
        <video id="scannerVideo" muted playsinline></v
```

### 52. NEEDS REVIEW — button route audit

**Location:** `templates/depart_driver_log.html:115`
**Selector:** `button:has-text('Stop Camera')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: Stop Camera
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
ScanBtn">Save Manual Scan</button>
      </div>
      <div class="scanner-stage" id="scannerStage">
        <video id="scannerVideo" muted playsinline></video>
        <div class="mt-2 d-flex gap-2 flex-wrap">
          <button class="btn btn-sm btn-outline-danger" type="button" id="stopScannerBtn">Stop Camera</button>
          <span class="text-muted small" id="scanStatus">Waiting for barcode...</span>
        </div>
      </div>
```

### 53. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_live_route_map.html:202`
**Selector:** `button`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action:  class="route-map-drawer-backdrop" type="button" data-route-map-close aria-label
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
related record <span>Not wired yet.</span></button>{% endif %}
          </div>
        </div>
      {% endfor %}
    {% endif %}

    <div class="route-map-drawer" data-route-map-drawer hidden aria-hidden="true">
      <button class="route-map-drawer-backdrop" type="button" data-route-map-close aria-label="Close details"></button>
      <aside class="route-map-drawer-panel" role="dialog" aria-modal="true" aria-label="Production flow de
```

### 54. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_live_route_map.html:205`
**Selector:** `button:has-text('Close')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: Close
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
data-route-map-close aria-label="Close details"></button>
      <aside class="route-map-drawer-panel" role="dialog" aria-modal="true" aria-label="Production flow details">
        <div class="drawer-grip"></div>
        <button class="drawer-close" type="button" data-route-map-close>Close</button>
        <div data-route-map-drawer-content></div>
      </aside>
    </div>
  </section>
{% else %}
  <section class="route-map-shell" data-r
```

### 55. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_live_route_map.html:340`
**Selector:** `button`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action:  class="route-map-drawer-backdrop" type="button" data-route-map-close aria-label
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
y_message if rm and rm.map_empty_message else 'No active route or production-flow signals for this date.' }}</p>
	    {% endif %}

    <div class="route-map-drawer" data-route-map-drawer hidden aria-hidden="true">
      <button class="route-map-drawer-backdrop" type="button" data-route-map-close aria-label="Close details"></button>
      <aside class="route-map-drawer-panel" role="dialog" aria-modal="true" aria-label="Route map details"
```

### 56. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_live_route_map.html:343`
**Selector:** `button:has-text('Close')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: Close
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
tton" data-route-map-close aria-label="Close details"></button>
      <aside class="route-map-drawer-panel" role="dialog" aria-modal="true" aria-label="Route map details">
        <div class="drawer-grip"></div>
        <button class="drawer-close" type="button" data-route-map-close>Close</button>
        <div data-route-map-drawer-content></div>
      </aside>
    </div>

    {% include "partials/_stop_detail_drawer.html" %}
    {% inc
```

### 57. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_production_flow_map.html:714`
**Selector:** `button:has-text('{{ marker.display_label }} {{ marker.location_label }}{% if ')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: {{ marker.display_label }} {{ marker.location_label }}{% if marker.departure_at %} · departed{% else %} · open{% endif %}
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
class="flow-stream-section">
            <p class="flow-stream-title">Today&rsquo;s Route</p>
            <div class="route-proof-drawer">
              {% for marker in pf.route_overlay.stop_markers %}
                <button type="button"
                        class="route-proof-stop"
                        data-flow-open="item"
                        data-flow-id="route_stop-{{ marker.internal_stop_id }}"
```

### 58. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_production_flow_map.html:844`
**Selector:** `button:has-text('{{ object.label }} {{ object.count }} {{ object.headline }} ')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: {{ object.label }} {{ object.count }} {{ object.headline }} {% if object.detail %} {{ object.detail }} {% endif %}
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
</svg>

              <div class="map-html-layer">
                <div class="flow-object-layer" aria-label="Primary flow objects" hidden>
                  {% for object in pf.flow_objects %}
                    <button type="button"
                            class="flow-object-card flow-object-card--{{ object.status }}"
                            data-flow-open="object"
                            data-flow-id="{{ object.key
```

### 59. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_production_flow_map.html:874`
**Selector:** `button:has-text("{{ (item.display_label or item.label)|truncate(10,true,'') }")`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: {{ (item.display_label or item.label)|truncate(10,true,'') }} {{ badge_text or item.status_label|truncate(7,true,'') }} {% if item.item_type == 'route_stop' %} {{ (item.plant_location or item.stage or '\u2014')|truncate(15,true,'') }} {{ (item.next_action or item.status_label or '')|truncate(17,true,'') }} {% else %} {{ (item.cargo_text or item.description or item.stage or '\u2014')|truncate(18,true,'') }} {{ (item.assigned_driver or item.next_action or '')|truncate(18,true,'') }} {% endif %}
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
class = 'chip-badge chip-badge--waiting' %}
                    {% elif item.priority in ('hot','safety') %}{% set badge_text = 'HOT' %}{% set badge_class = 'chip-badge chip-badge--hot' %}{% endif %}
                    <button type="button"
                            class="flow-chip{% if item.item_type == 'route_stop' %} route-step-chip{% endif %} flow-chip--{{ item.status }}"
                            style="{% if item.layout %}le
```

### 60. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_production_flow_map.html:907`
**Selector:** `button:has-text('{{ display_name }} {{ profile.role_label }} {{ profile.descr')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: {{ display_name }} {{ profile.role_label }} {{ profile.description }} {% if node.hot_count %} Hot part{% if node.hot_count > 1 %} x{{ node.hot_count }}{% endif %} {% endif %} {{ profile.primary_label }}: {{ profile.primary_value }} {{ profile.secondary_label }}: {{ profile.secondary_value }}
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
{% set profile = node.production_profile %}
                    {% set display_name = node.label ~ (' (' ~ node.short_code ~ ')' if node.short_code and node.short_code != node.label else '') %}
                    <button type="button"
                            class="flow-node production-node-card production-node-card--{{ profile.size }} production-node-card--{{ profile.theme }} flow-node--{{ node.worst_status }}{% if node.hot_
```

### 61. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_production_flow_map.html:1686`
**Selector:** `button:has-text('Close \\u2715')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: Close \u2715
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
ateConsole(trigger, null);
        renderFilteredEdges(trigger);
        if (globalView) globalView.hidden = isMobileFlow;
        if (detailView) {
          detailView.hidden = false;
          detailView.innerHTML = '<button type="button" class="drawer-close" data-flow-close aria-label="Close details">Close \u2715</button>' + source.innerHTML;
        }
        var drawer = root.querySelector('[data-flow-drawer]');
        if (drawer
```

### 62. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_production_flow_drawer.html:169`
**Selector:** `button`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action:  class="route-map-drawer-backdrop" type="button" data-route-map-close aria-label
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
led>Open related record <span>Requires authorized identity.</span></button>{% endif %}
      </div>
    </div>
  {% endfor %}
{% endif %}

<div class="route-map-drawer" data-route-map-drawer hidden aria-hidden="true">
  <button class="route-map-drawer-backdrop" type="button" data-route-map-close aria-label="Close details"></button>
  <aside class="route-map-drawer-panel" role="dialog" aria-modal="true" aria-label="Production flow detail
```

### 63. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_production_flow_drawer.html:172`
**Selector:** `button:has-text('Close')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: Close
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
pe="button" data-route-map-close aria-label="Close details"></button>
  <aside class="route-map-drawer-panel" role="dialog" aria-modal="true" aria-label="Production flow details">
    <div class="drawer-grip"></div>
    <button class="drawer-close" type="button" data-route-map-close>Close</button>
    <div data-route-map-drawer-content></div>
  </aside>
</div>
```

### 64. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_compact_route_map.html:379`
**Selector:** `button`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action:  class="md-flow-work-scrim" type="button" data-md-flow-close aria-label="Close q
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
bel="Replay mode. Actions disabled.">
      <span>REPLAY MODE</span><i aria-hidden="true"></i><span>ACTIONS DISABLED</span>
    </div>
  {% endif %}

  <div class="md-flow-work-panel" data-md-flow-work-panel hidden>
    <button class="md-flow-work-scrim" type="button" data-md-flow-close aria-label="Close quick action"></button>
    <div class="md-flow-work-card" role="dialog" aria-modal="true" aria-labelledby="liveFlowWorkTitle">
```

### 65. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_compact_route_map.html:386`
**Selector:** `button:has-text('Close')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: Close
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
s="md-flow-work-head">
        <div>
          <span data-md-flow-work-kicker>QUICK ACTION MODAL</span>
          <strong id="liveFlowWorkTitle" data-md-flow-work-title>Route quick action</strong>
        </div>
        <button type="button" data-md-flow-close>Close</button>
      </div>
      <div class="md-flow-context" data-md-flow-context></div>
      <div class="md-flow-inline-panel depart-quick-flow" data-flow-inline-panel="depart
```

### 66. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_compact_route_map.html:421`
**Selector:** `button:has-text('Yes')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: Yes
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
heck %}Did you unload and drop off cargo?{% elif requires_secondary_drop_check %}Did you drop off this cargo?{% else %}Did you get unloaded?{% endif %}</h4>
              <div class="depart-choice-grid">
                <button type="button" data-depart-choice data-field="unloaded_on_departure" data-value="yes" data-mirror-secondary="true" data-next-step="{{ 1 if not is_service_depart else 4 }}">Yes</button>
                {% if not is
```

### 67. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_compact_route_map.html:423`
**Selector:** `button:has-text('No')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: No
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
ice data-field="unloaded_on_departure" data-value="yes" data-mirror-secondary="true" data-next-step="{{ 1 if not is_service_depart else 4 }}">Yes</button>
                {% if not is_service_depart %}
                  <button type="button" data-depart-choice data-field="unloaded_on_departure" data-value="no" data-mirror-secondary="true" data-show-reason="unload">No</button>
                {% endif %}
              </div>
```

### 68. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_compact_route_map.html:432`
**Selector:** `button:has-text('Continue')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: Continue
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
n">Why not?</label>
                <textarea id="departUnloadReason" data-depart-text="unload_reason" data-mirror-text="secondary_unload_reason" placeholder="Short reason for manager review"></textarea>
                <button type="button" data-depart-next="1">Continue</button>
              </div>
            </section>
            <section class="depart-step {% if start_depart_step == 1 %}is-active{% endif %}" data-depart-step="1">
```

### 69. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_compact_route_map.html:439`
**Selector:** `button:has-text('Yes')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: Yes
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
1 %}is-active{% endif %}" data-depart-step="1">
              <span class="depart-step-kicker">load check</span>
              <h4>Did you get loaded?</h4>
              <div class="depart-choice-grid">
                <button type="button" data-depart-choice data-field="got_loaded" data-value="yes" data-next-step="2">Yes</button>
                <button type="button" data-depart-choice data-field="got_loaded" data-value="no" data-next
```

### 70. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_compact_route_map.html:440`
**Selector:** `button:has-text('No')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: No
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
4>Did you get loaded?</h4>
              <div class="depart-choice-grid">
                <button type="button" data-depart-choice data-field="got_loaded" data-value="yes" data-next-step="2">Yes</button>
                <button type="button" data-depart-choice data-field="got_loaded" data-value="no" data-next-step="3">No</button>
              </div>
            </section>
            <section class="depart-step" data-depart-step="2">
```

### 71. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_compact_route_map.html:469`
**Selector:** `button:has-text('Back')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: Back
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
/select>
              </div>
              <p class="depart-error" data-depart-error hidden>Select a destination before confirming a loaded departure.</p>
              <div class="depart-step-actions">
                <button type="button" data-depart-prev="1">Back</button>
                <button type="button" data-depart-next="3" data-require-destination>Continue</button>
              </div>
            </section>
            <sect
```

### 72. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_compact_route_map.html:470`
**Selector:** `button:has-text('Continue')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: Continue
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
depart-error hidden>Select a destination before confirming a loaded departure.</p>
              <div class="depart-step-actions">
                <button type="button" data-depart-prev="1">Back</button>
                <button type="button" data-depart-next="3" data-require-destination>Continue</button>
              </div>
            </section>
            <section class="depart-step" data-depart-step="3">
              <span class="
```

### 73. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_compact_route_map.html:477`
**Selector:** `button:has-text('No issue')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: No issue
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
t-step" data-depart-step="3">
              <span class="depart-step-kicker">exception check</span>
              <h4>Any damage, issue, or proof note?</h4>
              <div class="depart-choice-grid">
                <button type="button" data-depart-choice data-field="cargo_override_reason" data-value="" data-next-step="4">No issue</button>
                <a class="depart-risk-link" href="{{ damage_url or '#' }}">&#9650; Damage / m
```

### 74. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_compact_route_map.html:483`
**Selector:** `button:has-text('Back')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: Back
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
>
              <textarea id="departProofNote" data-depart-text="cargo_override_reason" placeholder="Short note only if something needs review"></textarea>
              <div class="depart-step-actions">
                <button type="button" data-depart-prev="2">Back</button>
                <button type="button" data-depart-next="4">Continue</button>
              </div>
            </section>
            <section class="depart-step" d
```

### 75. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_compact_route_map.html:484`
**Selector:** `button:has-text('Continue')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: Continue
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
erride_reason" placeholder="Short note only if something needs review"></textarea>
              <div class="depart-step-actions">
                <button type="button" data-depart-prev="2">Back</button>
                <button type="button" data-depart-next="4">Continue</button>
              </div>
            </section>
            <section class="depart-step" data-depart-step="4">
              <span class="depart-step-kicker">confi
```

### 76. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_compact_route_map.html:497`
**Selector:** `button:has-text('Back')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: Back
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
ion">--</strong></div>
                <div><span>Second</span><strong data-depart-summary="secondary_destination">NONE</strong></div>
              </div>
              <div class="depart-step-actions">
                <button type="button" data-depart-prev="3">Back</button>
                <button class="depart-submit" type="submit">Record Departure</button>
              </div>
              <a class="md-flow-panel-link ghost" href="
```

### 77. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_compact_route_map.html:640`
**Selector:** `button:has-text('{{ task.title }} {% if task.part_number %} &middot; Part {{ ')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: {{ task.title }} {% if task.part_number %} &middot; Part {{ task.part_number }}{% elif task.details %} &middot; {{ task.details|truncate(38, true) }}{% endif %} {{ task_status_text }}
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
else task.status.replace('-', ' ')|upper %}
            {% set task_status_tone = 'hot' if task.is_hot else ('open' if task.status == 'in-progress' else ('empty' if task.status == 'pending' else 'ready')) %}
            <button class="md-flow-row tone-{{ 'hot' if task.is_hot else 'active' }}" type="button"
                    data-flow-row
                    data-detail-template="task-{{ loop.index0 }}"
                    data-title="
```

### 78. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_compact_route_map.html:656`
**Selector:** `button:has-text('{{ item.code }} {{ item.text }} {{ item_badge.short }}')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: {{ item.code }} {{ item.text }} {{ item_badge.short }}
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
atus status-{{ task_status_tone }}">{{ task_status_text }}</span>
	            </button>
          {% endfor %}
          {% for item in ops_board_items %}
            {% set item_badge = item.board_badge %}
            <button class="md-flow-row tone-{{ item_badge.row_tone }}" type="button"
                    data-flow-row
                    data-detail-template="ops-item-{{ loop.index0 }}"
                    data-title="{{ item.tit
```

### 79. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_compact_route_map.html:672`
**Selector:** `button:has-text('{{ board_flow_text(stop.board_flow, stop.board_detail or (st')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: {{ board_flow_text(stop.board_flow, stop.board_detail or (stop.plant_name ~ ' · ' ~ stop.arrived_with ~ ' → ' ~ stop.departed_with), stop.wait_minutes) }} {{ stop_badge.short }}
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
</button>
          {% endfor %}
          {% for stop in board_route_stops %}
            {% set stop_badge = stop.board_badge if stop.board_badge is defined and stop.board_badge else stop.badge %}
            <button class="md-flow-row tone-{{ stop_badge.row_tone }}{% if stop.status == 'completed' and stop_badge.row_tone != 'active' %} is-completed-stop{% endif %}" type="button"
                    data-flow-row
```

### 80. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_desktop_ops_workspace.html:90`
**Selector:** `button:has-text('{{ label }} {{ value }} {{ detail }}')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: {{ label }} {{ value }} {{ detail }}
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
t"><span>{{ label }}</span><strong>{{ clean_value(value, action) }}</strong></div>
{%- endmacro %}

{% macro metric_tile(label, value, detail, mode=none, template=none, alert=false) -%}
  {%- if mode or template -%}
    <button class="desk-metric-tile{% if alert %} has-alert{% endif %}" type="button" {% if template %}data-desktop-select-template="{{ template }}"{% else %}data-desktop-mode="{{ mode }}"{% endif %} aria-label="{{ label }}:
```

### 81. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_desktop_ops_workspace.html:101`
**Selector:** `button:has-text('{{ code }} {% if stop_label %} {{ stop_label }} {% endif %} ')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: {{ code }} {% if stop_label %} {{ stop_label }} {% endif %} {{ title }} {{ clean_value(meta) }}
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
span>{{ label }}</span><strong>{{ value }}</strong><small>{{ detail }}</small>
    </div>
  {%- endif -%}
{%- endmacro %}

{% macro row_button(key, code, title, meta, tone='normal', default=false, stop_label=none) -%}
  <button class="desk-ops-row tone-{{ tone }}{% if stop_label %} has-stop-number{% endif %}" type="button" data-desktop-row data-detail-template="{{ key }}" {% if default %}data-desktop-default="true"{% endif %}>
    <span
```

### 82. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_desktop_ops_workspace.html:207`
**Selector:** `button:has-text('Attach Document')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: Attach Document
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
_user.department %} &middot; {{ current_user.department|lower }}{% endif %}</small>
            <div class="desk-staged-actions">
              {% if current_action_is_document and not route_finalized %}
                <button class="desk-current-cta" type="button" data-desktop-mode="documents">Attach Document</button>
              {% elif action_is_depart %}
                {% if current_stop and cta_urls.get('record_departure') %}<a
```

### 83. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_desktop_ops_workspace.html:238`
**Selector:** `button:has-text('Overview')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: Overview
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
te Workspace</span>
          <strong data-desktop-work-title>Route object detail</strong>
        </div>
        <div class="desk-work-tabs" data-desktop-work-tabs role="tablist" aria-label="Workspace modes">
          <button type="button" data-desktop-mode="overview" class="is-active">Overview</button>
          <button type="button" data-desktop-mode="route-packet">Route Packet</button>
          <button type="button" data-desktop-m
```

### 84. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_desktop_ops_workspace.html:239`
**Selector:** `button:has-text('Route Packet')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: Route Packet
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
</div>
        <div class="desk-work-tabs" data-desktop-work-tabs role="tablist" aria-label="Workspace modes">
          <button type="button" data-desktop-mode="overview" class="is-active">Overview</button>
          <button type="button" data-desktop-mode="route-packet">Route Packet</button>
          <button type="button" data-desktop-mode="documents">Documents</button>
          <button type="button" data-desktop-mode="issues">Iss
```

### 85. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_desktop_ops_workspace.html:240`
**Selector:** `button:has-text('Documents')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: Documents
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
-label="Workspace modes">
          <button type="button" data-desktop-mode="overview" class="is-active">Overview</button>
          <button type="button" data-desktop-mode="route-packet">Route Packet</button>
          <button type="button" data-desktop-mode="documents">Documents</button>
          <button type="button" data-desktop-mode="issues">Issues</button>
          <button type="button" data-desktop-mode="inspections">Inspection
```

### 86. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_desktop_ops_workspace.html:241`
**Selector:** `button:has-text('Issues')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: Issues
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
view" class="is-active">Overview</button>
          <button type="button" data-desktop-mode="route-packet">Route Packet</button>
          <button type="button" data-desktop-mode="documents">Documents</button>
          <button type="button" data-desktop-mode="issues">Issues</button>
          <button type="button" data-desktop-mode="inspections">Inspections</button>
          <button type="button" data-desktop-mode="log">Log</button>
```

### 87. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_desktop_ops_workspace.html:242`
**Selector:** `button:has-text('Inspections')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: Inspections
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
ata-desktop-mode="route-packet">Route Packet</button>
          <button type="button" data-desktop-mode="documents">Documents</button>
          <button type="button" data-desktop-mode="issues">Issues</button>
          <button type="button" data-desktop-mode="inspections">Inspections</button>
          <button type="button" data-desktop-mode="log">Log</button>
        </div>
        <div class="desk-work-body" data-desktop-work-body>
```

### 88. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_desktop_ops_workspace.html:243`
**Selector:** `button:has-text('Log')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: Log
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
data-desktop-mode="documents">Documents</button>
          <button type="button" data-desktop-mode="issues">Issues</button>
          <button type="button" data-desktop-mode="inspections">Inspections</button>
          <button type="button" data-desktop-mode="log">Log</button>
        </div>
        <div class="desk-work-body" data-desktop-work-body>
          <p class="desk-empty">Select an operation on the left to inspect documents,
```

### 89. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_desktop_ops_workspace.html:326`
**Selector:** `button:has-text("{{ 'Review Route Packet' if route_finalized else 'Attach to ")`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: {{ 'Review Route Packet' if route_finalized else 'Attach to Route Packet' }}
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
<span>Route Packet:</span>
            <strong>{{ documents_attached }} attached &middot; {% if documents_needed %}{{ documents_needed }} required flagged{% else %}none required flagged{% endif %}</strong>
            <button class="desk-inline-mode-link" type="button" data-desktop-mode="route-packet">{{ 'Review Route Packet' if route_finalized else 'Attach to Route Packet' }}</button>
          </section>
          {% if log and not
```

### 90. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_desktop_ops_workspace.html:358`
**Selector:** `button:has-text("{{ 'Review Route Packet' if route_finalized else 'Attach to ")`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: {{ 'Review Route Packet' if route_finalized else 'Attach to Route Packet' }}
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
<span>Route Packet:</span>
            <strong>{{ documents_attached }} attached &middot; {% if documents_needed %}{{ documents_needed }} required flagged{% else %}none required flagged{% endif %}</strong>
            <button class="desk-inline-mode-link" type="button" data-desktop-mode="route-packet">{{ 'Review Route Packet' if route_finalized else 'Attach to Route Packet' }}</button>
          </section>
          <div class="desk-o
```

### 91. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_desktop_ops_workspace.html:361`
**Selector:** `button:has-text('Review route packet')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: Review route packet
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
ry-action">
            {% if detail and detail.stop_id and not route_finalized %}<a class="desk-action-link primary" href="{{ url_for('driver.edit_driver_log', log_id=detail.stop_id) }}">Change destination</a>{% else %}<button class="desk-action-link primary" type="button" data-desktop-mode="route-packet">Review route packet</button>{% endif %}
          </div>
        </div>
      </template>
    {% endfor %}

    {% for transfer in r
```

### 92. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_desktop_ops_workspace.html:424`
**Selector:** `button:has-text('DOC Transfer sheet needed {{ packet_transfer_load.title if p')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: DOC Transfer sheet needed {{ packet_transfer_load.title if packet_transfer_load else 'Recorded route load' }} has no transfer sheet or route transfer record attached.
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
!= 1 else '' }} need document review before export.</span></div>
            <div class="desk-evidence-list" aria-label="Required route packet flags">
              {% if route_packet_missing_transfer %}
                <button class="desk-evidence-row desk-mode-row" type="button" data-desktop-select-template="desktop-route-packet-transfer-sheet">
                  <span>DOC</span>
                  <strong>Transfer sheet needed</strong
```

### 93. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_desktop_ops_workspace.html:433`
**Selector:** `button:has-text('DOC {{ issue.label }} {{ stop.plant_name }} &middot; {{ issu')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: DOC {{ issue.label }} {{ stop.plant_name }} &middot; {{ issue.action }}
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
{% endif %}
              {% for stop in rm.stops|default([]) if rm %}
                {% for issue in stop.issues|default([]) %}
                  {% if issue.code == 'missing_proof' %}
                    <button class="desk-evidence-row desk-mode-row" type="button" data-desktop-select-template="desktop-issue-{{ stop.stop_id }}-{{ issue.code }}">
                      <span>DOC</span>
                      <strong>{{ issu
```

### 94. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_desktop_ops_workspace.html:448`
**Selector:** `button:has-text('Review documents')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: Review documents
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
e"><span>Print / Export</span><strong>Packet controls</strong></div>
          <div class="desk-action-grid">
            <a class="desk-action-link primary" href="{{ route_audit_url }}">Open route audit</a>
            <button class="desk-action-link" type="button" data-desktop-mode="documents">Review documents</button>
            <a class="desk-action-link" href="{{ url_for('driver.list_pretrips', truck_number=current_truck_number) i
```

### 95. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_desktop_ops_workspace.html:572`
**Selector:** `button:has-text('DOC Transfer sheet needed {{ packet_transfer_load.title if p')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: DOC Transfer sheet needed {{ packet_transfer_load.title if packet_transfer_load else 'Recorded route load' }} &middot; Add the missing route packet document.
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
iv class="desk-section-title"><span>Current Issues</span><strong>{{ attention_count }} attention</strong></div>
          <div class="desk-evidence-list">
            {% if route_packet_missing_transfer %}
              <button class="desk-evidence-row desk-mode-row" type="button" data-desktop-select-template="desktop-route-packet-transfer-sheet">
                <span>DOC</span>
                <strong>Transfer sheet needed</strong>
```

### 96. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_desktop_ops_workspace.html:581`
**Selector:** `button:has-text('{{ issue.severity|upper }} {{ issue.label }} {{ stop.plant_n')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: {{ issue.severity|upper }} {{ issue.label }} {{ stop.plant_name }} &middot; {{ issue.action }}
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
utton>
            {% endif %}
            {% for stop in rm.stops|default([]) if rm %}
              {% for issue in stop.issues|default([]) %}
                {% if issue.code != 'needs_departure' %}
                  <button class="desk-evidence-row desk-mode-row" type="button" data-desktop-select-template="desktop-issue-{{ stop.stop_id }}-{{ issue.code }}">
                    <span>{{ issue.severity|upper }}</span>
```

### 97. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_desktop_ops_workspace.html:590`
**Selector:** `button:has-text('DAMAGE {{ report.plant_name }} {{ report.description }}')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: DAMAGE {{ report.plant_name }} {{ report.description }}
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
_name }} &middot; {{ issue.action }}</small>
                  </button>
                {% endif %}
              {% endfor %}
            {% endfor %}
            {% for report in route_damage_reports %}
              <button class="desk-evidence-row desk-mode-row" type="button" data-desktop-select-template="desktop-damage-{{ report.id }}">
                <span>DAMAGE</span>
                <strong>{{ report.plant_name }}</strong>
```

### 98. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_desktop_ops_workspace.html:597`
**Selector:** `button:has-text('INSP PostTrip pending Close the route with a PostTrip to cap')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: INSP PostTrip pending Close the route with a PostTrip to capture end mileage, fuel, and miles driven.
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
span>
                <strong>{{ report.plant_name }}</strong>
                <small>{{ report.description }}</small>
              </button>
            {% endfor %}
            {% if pending_posttrip %}
              <button class="desk-evidence-row desk-mode-row" type="button" data-desktop-mode="inspections">
                <span>INSP</span>
                <strong>PostTrip pending</strong>
                <small>Close the route wi
```

### 99. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_desktop_ops_workspace.html:617`
**Selector:** `button:has-text("{{ 'DONE' if dl.depart_time else 'OPEN' }} {{ dl.plant_name ")`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: {{ 'DONE' if dl.depart_time else 'OPEN' }} {{ dl.plant_name }} Arrived {{ dl.arrive_time|display_time if dl.arrive_time else 'not recorded' }} &middot; Departed {{ dl.depart_time|to_12h_format if dl.depart_time else 'pending' }}
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
imeline</span><strong>{{ todays_logs|length }} stop{{ 's' if todays_logs|length != 1 else '' }}</strong></div>
          <div class="desk-evidence-list">
            {% for dl in todays_logs|default([]) %}
              <button class="desk-evidence-row desk-mode-row" type="button" data-desktop-select-template="desktop-stop-{{ dl.id }}">
                <span>{{ 'DONE' if dl.depart_time else 'OPEN' }}</span>
                <strong>{{ dl
```

### 100. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_desktop_ops_workspace.html:660`
**Selector:** `button:has-text('Open documents')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: Open documents
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
tch' %}<a class="desk-action-link primary" href="{{ url_for('driver.edit_driver_log', log_id=log.id) }}">Confirm destination</a>{% endif %}
                    {% if issue.code in ['missing_proof', 'unconfirmed_drop'] %}<button class="desk-action-link primary" type="button" data-desktop-mode="documents">Open documents</button>{% endif %}
                    <a class="desk-action-link" href="{{ url_for('driver.edit_driver_log', log_id=lo
```

### 101. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_desktop_ops_workspace.html:690`
**Selector:** `button:has-text('Open Documents')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: Open Documents
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
</section>
          <section class="desk-detail-section">
            <div class="desk-section-title"><span>Actions</span><strong>Packet controls</strong></div>
            <div class="desk-action-grid">
              <button class="desk-action-link primary" type="button" data-desktop-mode="documents">Open Documents</button>
              <button class="desk-action-link" type="button" data-desktop-mode="route-packet">Back to Route Pac
```

### 102. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_desktop_ops_workspace.html:691`
**Selector:** `button:has-text('Back to Route Packet')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: Back to Route Packet
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
><strong>Packet controls</strong></div>
            <div class="desk-action-grid">
              <button class="desk-action-link primary" type="button" data-desktop-mode="documents">Open Documents</button>
              <button class="desk-action-link" type="button" data-desktop-mode="route-packet">Back to Route Packet</button>
              <a class="desk-action-link" href="{{ url_for('driver.driver_logs', date=route_date.isoformat() i
```

### 103. NEEDS REVIEW — button route audit

**Location:** `templates/partials/_md_toasts.html:100`
**Selector:** `button:has-text('&times;')`
**Expected:** Every visible button has a real submit/action route, click handler, or intentional disabled state.
**Actual:** Button appears to lack an action: &times;
**Recommendation:** Wire the button to a real route/action or mark it intentionally disabled with visible copy and tests.

```text
ata-type', type || 'success');
      node.innerHTML = '<i class="md-toast-dot" aria-hidden="true"></i>' +
        '<span><strong class="md-toast-title"></strong><small class="md-toast-detail"></small></span>' +
        '<button type="button" class="md-toast-close" aria-label="Dismiss">&times;</button>';
      node.querySelector('.md-toast-title').textContent = title || 'RECORDED';
      node.querySelector('.md-toast-detail').textContent
```

### 104. NEEDS REVIEW — form submit audit

**Location:** `templates/all_in_one_dashboard.html:300`
**Selector:** `form`
**Expected:** Forms should declare where data is submitted or clearly rely on current route with tests.
**Actual:** Form has no explicit action/hx-post/data-action.
**Recommendation:** Add an explicit action or document/test the current-route submit behavior.

```text
</li>
      {% endfor %}
      </ul>
    {% else %}
      <p>No announcements found.</p>
    {% endif %}

    <hr>

    <!-- 4) Direct MESSAGES inline (like a quick DM panel) -->
    <h3>Send a Direct Message</h3>
    <form method="POST">
      {{ dm_form.hidden_tag() }}
      <div class="form-group">
        <label>Send To (User/Driver):</label>
        {{ dm_form.receiver_id(class="form-control") }}
      </div>
      <div class="fo
```

### 105. NEEDS REVIEW — form submit audit

**Location:** `templates/chat.html:11`
**Selector:** `form`
**Expected:** Forms should declare where data is submitted or clearly rely on current route with tests.
**Actual:** Form has no explicit action/hx-post/data-action.
**Recommendation:** Add an explicit action or document/test the current-route submit behavior.

```text
="border: 1px solid #ccc; padding: 10px; height: 300px; overflow-y: scroll;">
    {% for msg in messages %}
      <div><strong>{{ msg.user.username }}:</strong> {{ msg.content }}</div>
    {% endfor %}
  </div>
  <hr>
  <form id="chat-form">
    <div class="mb-3">
      <textarea id="chat-input" class="form-control" rows="3" placeholder="Type your message..."></textarea>
    </div>
    <button type="submit" class="btn btn-primary">Send<
```

### 106. NEEDS REVIEW — form submit audit

**Location:** `templates/chat.html:11`
**Selector:** `form`
**Expected:** Forms that mutate state should use an explicit method.
**Actual:** Form has no explicit method.
**Recommendation:** Set method='post' for mutations or explicitly mark as GET/search.

```text
="border: 1px solid #ccc; padding: 10px; height: 300px; overflow-y: scroll;">
    {% for msg in messages %}
      <div><strong>{{ msg.user.username }}:</strong> {{ msg.content }}</div>
    {% endfor %}
  </div>
  <hr>
  <form id="chat-form">
    <div class="mb-3">
      <textarea id="chat-input" class="form-control" rows="3" placeholder="Type your message..."></textarea>
    </div>
    <button type="submit" class="btn btn-primary">Send<
```

### 107. NEEDS REVIEW — form submit audit

**Location:** `templates/do_posttrip.html:8`
**Selector:** `form`
**Expected:** Forms should declare where data is submitted or clearly rely on current route with tests.
**Actual:** Form has no explicit action/hx-post/data-action.
**Recommendation:** Add an explicit action or document/test the current-route submit behavior.

```text
%}
{% block title %}Complete PostTrip{% endblock %}

{% block content %}
<script>document.body.classList.add('md-shell');</script>
{% include 'partials/_md_shell.html' %}
<h2>PostTrip for PreTrip #{{ pretrip.id }}</h2>
<form method="POST" class="row g-3 md-glass md-glow p-3" data-autosave="true" data-autosave-key="posttrip-{{ pretrip.id }}">
  {{ form.hidden_tag() }}

  <div class="col-md-6">
    <label for="end_mileage" class="form-la
```

### 108. NEEDS REVIEW — form submit audit

**Location:** `templates/editing_task.html:5`
**Selector:** `form`
**Expected:** Forms should declare where data is submitted or clearly rely on current route with tests.
**Actual:** Form has no explicit action/hx-post/data-action.
**Recommendation:** Add an explicit action or document/test the current-route submit behavior.

```text
{% extends "base.html" %}
{% block title %}Edit Task #{{ task_id }}{% endblock %}
{% block content %}
<h2>Edit Task #{{ task_id }}</h2>
<form method="POST" class="row g-3">
  {{ form.hidden_tag() }}

  <div class="col-md-6">
    <label for="title" class="form-label">{{ form.title.label }}</label>
    {{ form.title(class="form-control", id="title") }}
```

### 109. NEEDS REVIEW — form submit audit

**Location:** `templates/manager_dashboard.html:450`
**Selector:** `form`
**Expected:** Forms should declare where data is submitted or clearly rely on current route with tests.
**Actual:** Form has no explicit action/hx-post/data-action.
**Recommendation:** Add an explicit action or document/test the current-route submit behavior.

```text
<div class="mctx-item right">
          <p>Truck ID</p>
          <p id="mgTruck">—</p>
        </div>
      </div>

      {# Task section (editable inline) #}
      <div id="mgTaskSec" style="display:none;">
        <form id="mgTaskForm" method="POST" style="display:contents;">
          <input type="hidden" name="csrf_token" id="mgCSRF">

          <div>
            <label class="flbl">Assign / Reassign Driver</label>
            <
```

### 110. NEEDS REVIEW — form submit audit

**Location:** `templates/new_tip.html:6`
**Selector:** `form`
**Expected:** Forms should declare where data is submitted or clearly rely on current route with tests.
**Actual:** Form has no explicit action/hx-post/data-action.
**Recommendation:** Add an explicit action or document/test the current-route submit behavior.

```text
<!-- file: templates/new_tip.html -->
{% extends 'base.html' %}
{% block content %}
<div class="container">
  <h2>Add New Tip</h2>
  <form method="POST">
    <!-- Since we’re not using a FlaskForm for this in the example,
         just do normal form fields. Adjust as needed. -->
    <div class="mb-3">
      <label for="title" class="form-label">Tip T
```

### 111. NEEDS REVIEW — form submit audit

**Location:** `templates/unified_dashboard.html:207`
**Selector:** `form`
**Expected:** Forms should declare where data is submitted or clearly rely on current route with tests.
**Actual:** Form has no explicit action/hx-post/data-action.
**Recommendation:** Add an explicit action or document/test the current-route submit behavior.

```text
rrent_user.role|capitalize }}</h2>
    <hr>

    <!-- If manager, show create_task_section -->
    {% if is_management %}
    <div id="create_task_section" class="my-4 p-3 border">
      <h4>Create a New Task</h4>
      <form method="POST">
        {{ form_create_task.hidden_tag() }}

        <div class="form-group">
          <label>Title</label>
          {{ form_create_task.title(class="form-control") }}
        </div>
        <div c
```

### 112. NEEDS REVIEW — form submit audit

**Location:** `templates/unified_dashboard.html:316`
**Selector:** `form`
**Expected:** Forms should declare where data is submitted or clearly rely on current route with tests.
**Actual:** Form has no explicit action/hx-post/data-action.
**Recommendation:** Add an explicit action or document/test the current-route submit behavior.

```text
found.</p>
      {% endif %}
    </div>
    {% endif %}

    <!-- Direct messages form + inbox/outbox in same page -->
    <div id="direct_messages_section" class="my-4 p-3 border">
      <h4>Direct Messages</h4>
      <form method="POST">
        {{ dm_form.hidden_tag() }}
        <div class="form-group">
          <label>Send To (Driver or User)</label>
          {{ dm_form.receiver_id(class="form-control") }}
        </div>
```

### 113. NEEDS REVIEW — form submit audit

**Location:** `templates/manager_task_detail.html:119`
**Selector:** `form`
**Expected:** Forms should declare where data is submitted or clearly rely on current route with tests.
**Actual:** Form has no explicit action/hx-post/data-action.
**Recommendation:** Add an explicit action or document/test the current-route submit behavior.

```text
e('-', ' ')|title }}</p>
      </div>
    </section>

    <section class="detail-grid">
      <div class="panel">
        <div class="panel-head"><h2>Manager Actions</h2></div>
        <div class="panel-body">
          <form method="POST" class="manager-form" data-autosave="true" data-autosave-key="manager-task-{{ task.id }}">
            <div class="form-row">
              <div>
                <label for="assigned_to">Assign / Reass
```

### 114. NEEDS REVIEW — form submit audit

**Location:** `templates/manager_review.html:179`
**Selector:** `form`
**Expected:** Forms should declare where data is submitted or clearly rely on current route with tests.
**Actual:** Form has no explicit action/hx-post/data-action.
**Recommendation:** Add an explicit action or document/test the current-route submit behavior.

```text
endfor %}
            </tbody>
          </table>
        </div>
      </section>

      <details class="foldout" id="add-followup">
        <summary>Add Follow-up</summary>
        <div class="foldout-body">
          <form method="POST" class="row g-3">
            {{ form.hidden_tag() }}
            <div class="col-md-3">{{ form.kind.label(class="form-label") }}{{ form.kind(class="form-select") }}</div>
            <div class="col-m
```

### 115. NEEDS REVIEW — form submit audit

**Location:** `templates/damage_report_form.html:13`
**Selector:** `form`
**Expected:** Forms should declare where data is submitted or clearly rely on current route with tests.
**Actual:** Form has no explicit action/hx-post/data-action.
**Recommendation:** Add an explicit action or document/test the current-route submit behavior.

```text
xt-muted mb-0 small">Open reports remain editable until you submit them or finalize the route.</p>
    </div>
    <a class="btn btn-outline-secondary" href="{{ url_for('driver.damage_reports') }}">History</a>
  </div>
  <form method="POST" enctype="multipart/form-data" class="border rounded p-3 responsive-form-panel md-glow" data-autosave="true" data-autosave-key="damage-report-{{ report.id if report else 'new' }}">
    {{ form.hidden_t
```

### 116. NEEDS REVIEW — form submit audit

**Location:** `templates/manager/move_request_form.html:30`
**Selector:** `form`
**Expected:** Forms should declare where data is submitted or clearly rely on current route with tests.
**Actual:** Form has no explicit action/hx-post/data-action.
**Recommendation:** Add an explicit action or document/test the current-route submit behavior.

```text
ber if move_request else 'Create a durable intake record from the original request.' }}</p>
    </div>
    <a class="btn btn-outline-secondary" href="{{ url_for('manager.move_requests') }}">Back to Queue</a>
  </div>

  <form method="POST">
    {{ form.hidden_tag() }}
    <div class="request-card">
      <h2>Original Request / Message</h2>
      <div class="mb-3">
        {{ form.raw_text.label(class="form-label") }}
        {{ form.raw
```

### 117. NEEDS REVIEW — document upload audit

**Location:** `templates/_driver_log_photo_upload.html:43`
**Selector:** `input[type=file]`
**Expected:** Upload forms should use multipart/form-data unless uploads are handled purely by JavaScript FormData.
**Actual:** No multipart/form-data found near file input.
**Recommendation:** Confirm FormData JS handles upload or add enctype='multipart/form-data'.

```text
data-source="{{ photo_source_prefix }}_gallery">Upload From Gallery</button>
    <button class="secondary" type="button" data-stop-photo-trigger data-source="{{ photo_source_prefix }}_camera">Take New Photo</button>
    <input class="d-none" type="file" accept="image/*" data-stop-photo-input="{{ photo_source_prefix }}_gallery">
    <input class="d-none" type="file" accept="image/*" capture="environment" data-stop-photo-input="{{ photo_s
```

### 118. NEEDS REVIEW — document upload audit

**Location:** `templates/_driver_log_photo_upload.html:44`
**Selector:** `input[type=file]`
**Expected:** Upload forms should use multipart/form-data unless uploads are handled purely by JavaScript FormData.
**Actual:** No multipart/form-data found near file input.
**Recommendation:** Confirm FormData JS handles upload or add enctype='multipart/form-data'.

```text
utton" data-stop-photo-trigger data-source="{{ photo_source_prefix }}_camera">Take New Photo</button>
    <input class="d-none" type="file" accept="image/*" data-stop-photo-input="{{ photo_source_prefix }}_gallery">
    <input class="d-none" type="file" accept="image/*" capture="environment" data-stop-photo-input="{{ photo_source_prefix }}_camera">
  </div>
  <div class="stop-photo-status" data-stop-photo-status aria-live="polite"></div
```

### 119. NEEDS REVIEW — document upload audit

**Location:** `templates/partials/_desktop_ops_workspace.html:145`
**Selector:** `input[type=file]`
**Expected:** Upload forms should use multipart/form-data unless uploads are handled purely by JavaScript FormData.
**Actual:** No multipart/form-data found near file input.
**Recommendation:** Confirm FormData JS handles upload or add enctype='multipart/form-data'.

```text
al note<textarea name="note" rows="2" maxlength="500" placeholder="Only add detail if this needs review."></textarea></label>
        <div class="desk-attach-actions">
          <label class="desk-action-link">Take Photo<input type="file" name="photo" accept="image/*" capture="environment" onchange="if(this.files.length){this.form.submit();}"></label>
          <label class="desk-action-link">Upload File/Image<input type="file" name="ph
```

### 120. NEEDS REVIEW — document upload audit

**Location:** `templates/partials/_desktop_ops_workspace.html:146`
**Selector:** `input[type=file]`
**Expected:** Upload forms should use multipart/form-data unless uploads are handled purely by JavaScript FormData.
**Actual:** No multipart/form-data found near file input.
**Recommendation:** Confirm FormData JS handles upload or add enctype='multipart/form-data'.

```text
esk-action-link">Take Photo<input type="file" name="photo" accept="image/*" capture="environment" onchange="if(this.files.length){this.form.submit();}"></label>
          <label class="desk-action-link">Upload File/Image<input type="file" name="photo" accept="image/*" onchange="if(this.files.length){this.form.submit();}"></label>
        </div>
      </form>
    </details>
  {% endif %}
{%- endmacro %}

<section class="desktop-ops-works
```

### 121. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:944`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'forecast'. Use Next Load Estimate / Pickup Estimate / Timing Status instead.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
active{% endif %}" href="{{ url_for('manager.manager_dashboard', division=division_filter, driver_id=driver.id, focus='routes') }}">{{ driver.display_name }}</a>
          {% endfor %}
        </div>
        {% if plant_forecasts %}
        <div class="plant-timing-strip" aria-label="Plant load timing">
          {% for timing in plant_forecasts %}
            <div class="plant-timing-card">
              <strong>{{ timing.plant }}</str
```

### 122. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:946`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'forecast'. Use Next Load Estimate / Pickup Estimate / Timing Status instead.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
'routes') }}">{{ driver.display_name }}</a>
          {% endfor %}
        </div>
        {% if plant_forecasts %}
        <div class="plant-timing-strip" aria-label="Plant load timing">
          {% for timing in plant_forecasts %}
            <div class="plant-timing-card">
              <strong>{{ timing.plant }}</strong>
              {% if timing.estimate_minutes is none %}
                <span>No timing history yet</span>
```

### 123. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:996`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'forecast'. Use Next Load Estimate / Pickup Estimate / Timing Status instead.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
rted_delay_count %}<td class="align-middle whitespace-nowrap">{{ row.dock_wait }}</td>{% endif %}
                  <td class="align-middle">
                    <div class="timing-cell">
                      {% if row.forecast %}
                        <span class="timing-main">{{ row.forecast.estimate_label }}</span>
                        <span class="timing-sub">{% if row.forecast.ready_at_label %}Expected wait {{ row.forecast.re
```

### 124. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:997`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'forecast'. Use Next Load Estimate / Pickup Estimate / Timing Status instead.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
dock_wait }}</td>{% endif %}
                  <td class="align-middle">
                    <div class="timing-cell">
                      {% if row.forecast %}
                        <span class="timing-main">{{ row.forecast.estimate_label }}</span>
                        <span class="timing-sub">{% if row.forecast.ready_at_label %}Expected wait {{ row.forecast.ready_at_label }}{% else %}{{ row.forecast.confidence }}{% endif %}</sp
```

### 125. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:998`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'forecast'. Use Next Load Estimate / Pickup Estimate / Timing Status instead.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
<div class="timing-cell">
                      {% if row.forecast %}
                        <span class="timing-main">{{ row.forecast.estimate_label }}</span>
                        <span class="timing-sub">{% if row.forecast.ready_at_label %}Expected wait {{ row.forecast.ready_at_label }}{% else %}{{ row.forecast.confidence }}{% endif %}</span>
                        <span class="timing-state {{ row.forecast.severity }}">{{ row.for
```

### 126. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:998`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'forecast'. Use Next Load Estimate / Pickup Estimate / Timing Status instead.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
{% if row.forecast %}
                        <span class="timing-main">{{ row.forecast.estimate_label }}</span>
                        <span class="timing-sub">{% if row.forecast.ready_at_label %}Expected wait {{ row.forecast.ready_at_label }}{% else %}{{ row.forecast.confidence }}{% endif %}</span>
                        <span class="timing-state {{ row.forecast.severity }}">{{ row.forecast.status }}</span>
                      {%
```

### 127. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:998`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'forecast'. Use Next Load Estimate / Pickup Estimate / Timing Status instead.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
<span class="timing-main">{{ row.forecast.estimate_label }}</span>
                        <span class="timing-sub">{% if row.forecast.ready_at_label %}Expected wait {{ row.forecast.ready_at_label }}{% else %}{{ row.forecast.confidence }}{% endif %}</span>
                        <span class="timing-state {{ row.forecast.severity }}">{{ row.forecast.status }}</span>
                      {% else %}
                        <span clas
```

### 128. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:999`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'forecast'. Use Next Load Estimate / Pickup Estimate / Timing Status instead.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
an class="timing-sub">{% if row.forecast.ready_at_label %}Expected wait {{ row.forecast.ready_at_label }}{% else %}{{ row.forecast.confidence }}{% endif %}</span>
                        <span class="timing-state {{ row.forecast.severity }}">{{ row.forecast.status }}</span>
                      {% else %}
                        <span class="timing-main">Complete</span>
                        <span class="timing-sub">No active wait</s
```

### 129. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:999`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'forecast'. Use Next Load Estimate / Pickup Estimate / Timing Status instead.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
ow.forecast.ready_at_label %}Expected wait {{ row.forecast.ready_at_label }}{% else %}{{ row.forecast.confidence }}{% endif %}</span>
                        <span class="timing-state {{ row.forecast.severity }}">{{ row.forecast.status }}</span>
                      {% else %}
                        <span class="timing-main">Complete</span>
                        <span class="timing-sub">No active wait</span>
                      {%
```

### 130. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/driver_mobile.html:5380`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'forecast'. Use Next Load Estimate / Pickup Estimate / Timing Status instead.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
/form>
                {% endif %}
              </div>
            </article>
          {% endfor %}
        </div>
      </section>
      {% endif %}

	      {% if not board_only_home and current_stop and current_stop_forecast %}
      {% set fs = current_stop_forecast %}
      {% set current_route = (todays_log_routes or {}).get(current_stop.id) %}
      <section class="card timing-card">
        <div class="timing-top">
          <d
```

### 131. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/driver_mobile.html:5381`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'forecast'. Use Next Load Estimate / Pickup Estimate / Timing Status instead.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
</div>
            </article>
          {% endfor %}
        </div>
      </section>
      {% endif %}

	      {% if not board_only_home and current_stop and current_stop_forecast %}
      {% set fs = current_stop_forecast %}
      {% set current_route = (todays_log_routes or {}).get(current_stop.id) %}
      <section class="card timing-card">
        <div class="timing-top">
          <div>
            <p class="timing-title">{{
```

### 132. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/driver_mobile.html:5528`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'forecast'. Use Next Load Estimate / Pickup Estimate / Timing Status instead.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
t_number }}{% else %}{{ dl.part_number }}{% endif %}{% if wait_label %}{% if dl.part_number or dl.no_pickup %} - {% endif %}{{ wait_label }}{% endif %}
            </div>
            {% endif %}
            {% set panel_forecast = (stop_forecasts or {}).get(dl.id) %}
            {% if panel_forecast %}
              <div class="rp-parts">
                Timing status:
                {% if panel_forecast.estimate_minutes is not none %}
```

### 133. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/driver_mobile.html:5528`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'forecast'. Use Next Load Estimate / Pickup Estimate / Timing Status instead.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
e %}{{ dl.part_number }}{% endif %}{% if wait_label %}{% if dl.part_number or dl.no_pickup %} - {% endif %}{{ wait_label }}{% endif %}
            </div>
            {% endif %}
            {% set panel_forecast = (stop_forecasts or {}).get(dl.id) %}
            {% if panel_forecast %}
              <div class="rp-parts">
                Timing status:
                {% if panel_forecast.estimate_minutes is not none %}
```

### 134. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/driver_mobile.html:5529`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'forecast'. Use Next Load Estimate / Pickup Estimate / Timing Status instead.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
% if dl.part_number or dl.no_pickup %} - {% endif %}{{ wait_label }}{% endif %}
            </div>
            {% endif %}
            {% set panel_forecast = (stop_forecasts or {}).get(dl.id) %}
            {% if panel_forecast %}
              <div class="rp-parts">
                Timing status:
                {% if panel_forecast.estimate_minutes is not none %}
                  {{ panel_forecast.status }}{% if panel_forecast.ready
```

### 135. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/driver_mobile.html:5532`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'forecast'. Use Next Load Estimate / Pickup Estimate / Timing Status instead.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
{% endif %}
            {% set panel_forecast = (stop_forecasts or {}).get(dl.id) %}
            {% if panel_forecast %}
              <div class="rp-parts">
                Timing status:
                {% if panel_forecast.estimate_minutes is not none %}
                  {{ panel_forecast.status }}{% if panel_forecast.ready_at_label and not dl.depart_time %} · ready {{ panel_forecast.ready_at_label }}{% endif %}
                {
```

### 136. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/driver_mobile.html:5533`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'forecast'. Use Next Load Estimate / Pickup Estimate / Timing Status instead.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
r {}).get(dl.id) %}
            {% if panel_forecast %}
              <div class="rp-parts">
                Timing status:
                {% if panel_forecast.estimate_minutes is not none %}
                  {{ panel_forecast.status }}{% if panel_forecast.ready_at_label and not dl.depart_time %} · ready {{ panel_forecast.ready_at_label }}{% endif %}
                {% else %}
                  pending
                {% endif %}
```

### 137. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/driver_mobile.html:5533`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'forecast'. Use Next Load Estimate / Pickup Estimate / Timing Status instead.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
{% if panel_forecast %}
              <div class="rp-parts">
                Timing status:
                {% if panel_forecast.estimate_minutes is not none %}
                  {{ panel_forecast.status }}{% if panel_forecast.ready_at_label and not dl.depart_time %} · ready {{ panel_forecast.ready_at_label }}{% endif %}
                {% else %}
                  pending
                {% endif %}
              </div>
            {
```

### 138. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/driver_mobile.html:5533`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'forecast'. Use Next Load Estimate / Pickup Estimate / Timing Status instead.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
Timing status:
                {% if panel_forecast.estimate_minutes is not none %}
                  {{ panel_forecast.status }}{% if panel_forecast.ready_at_label and not dl.depart_time %} · ready {{ panel_forecast.ready_at_label }}{% endif %}
                {% else %}
                  pending
                {% endif %}
              </div>
            {% endif %}
            {% set stop_task_events = (route_task_events
```

### 139. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_review.html:91`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'forecast'. Use Next Load Estimate / Pickup Estimate / Timing Status instead.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
nassigned_issue_count }}</strong></div>
      </section>

      <details class="foldout" open>
        <summary>Plant Load Timing</summary>
        <div class="foldout-body timing-list">
          {% for timing in plant_forecasts %}
            <div class="timing-card">
              <strong>{{ timing.plant }}</strong>
              {% if timing.estimate_minutes is none %}
                <span>No timing history yet</span>
```

### 140. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_route_review.html:138`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'forecast'. Use Next Load Estimate / Pickup Estimate / Timing Status instead.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
p: {{ route_state.current_activity.plant }}.</strong> {{ route_state.current_activity.detail }}.</p>
      <p>{{ route_state.current_activity.pickup_estimate }}. <span class="delay-status {{ route_state.current_activity.forecast_class }}">{{ route_state.current_activity.forecast_status }}</span></p>
      {% if manager_intelligence %}
        <div class="audit-grid">
          {% for item in manager_intelligence %}<div class="audit-item
```

### 141. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_route_review.html:138`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'forecast'. Use Next Load Estimate / Pickup Estimate / Timing Status instead.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
g> {{ route_state.current_activity.detail }}.</p>
      <p>{{ route_state.current_activity.pickup_estimate }}. <span class="delay-status {{ route_state.current_activity.forecast_class }}">{{ route_state.current_activity.forecast_status }}</span></p>
      {% if manager_intelligence %}
        <div class="audit-grid">
          {% for item in manager_intelligence %}<div class="audit-item warning"><strong>Manager Intelligence</strong><spa
```

### 142. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_route_review.html:310`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'forecast'. Use Next Load Estimate / Pickup Estimate / Timing Status instead.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
top</th><th>Dock Time</th><th>Load-Time Status</th><th>Reason</th></tr></thead><tbody>
      {% for row in delay_review_rows %}<tr><td>{{ row.plant }}</td><td>{{ row.dock_wait }}</td><td><span class="delay-status {{ row.forecast_class }}">{{ row.forecast }}</span></td><td>{{ row.reason }}{% if row.requires_reason %}<br><strong>{{ row.action }}</strong>{% endif %}</td></tr>{% endfor %}
      </tbody></table>
    </div>
  </div>
  {% endi
```

### 143. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_route_review.html:310`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'forecast'. Use Next Load Estimate / Pickup Estimate / Timing Status instead.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
<th>Load-Time Status</th><th>Reason</th></tr></thead><tbody>
      {% for row in delay_review_rows %}<tr><td>{{ row.plant }}</td><td>{{ row.dock_wait }}</td><td><span class="delay-status {{ row.forecast_class }}">{{ row.forecast }}</span></td><td>{{ row.reason }}{% if row.requires_reason %}<br><strong>{{ row.action }}</strong>{% endif %}</td></tr>{% endfor %}
      </tbody></table>
    </div>
  </div>
  {% endif %}

  {% if logs %}
  <d
```

### 144. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_desktop_ops_workspace.html:227`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'forecast'. Use Next Load Estimate / Pickup Estimate / Timing Status instead.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
{{ metric_tile('Issues', route_damage_reports|length ~ ' damage', desk.mismatches ~ ' mismatch', 'issues', none, desk.issues > 0 or route_damage_reports|length > 0 or desk.mismatches > 0) }}
        {% if current_stop_forecast %}
          {{ metric_tile('Current Wait', current_stop_forecast.elapsed_label, 'Today avg ' ~ current_stop_forecast.today_average_label, none, 'desktop-stop-' ~ current_stop.id if current_stop else none) }}
```

### 145. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_desktop_ops_workspace.html:228`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'forecast'. Use Next Load Estimate / Pickup Estimate / Timing Status instead.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
, desk.mismatches ~ ' mismatch', 'issues', none, desk.issues > 0 or route_damage_reports|length > 0 or desk.mismatches > 0) }}
        {% if current_stop_forecast %}
          {{ metric_tile('Current Wait', current_stop_forecast.elapsed_label, 'Today avg ' ~ current_stop_forecast.today_average_label, none, 'desktop-stop-' ~ current_stop.id if current_stop else none) }}
        {% endif %}
      </div>

      <section class="desktop-deta
```

### 146. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_desktop_ops_workspace.html:228`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'forecast'. Use Next Load Estimate / Pickup Estimate / Timing Status instead.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
k.issues > 0 or route_damage_reports|length > 0 or desk.mismatches > 0) }}
        {% if current_stop_forecast %}
          {{ metric_tile('Current Wait', current_stop_forecast.elapsed_label, 'Today avg ' ~ current_stop_forecast.today_average_label, none, 'desktop-stop-' ~ current_stop.id if current_stop else none) }}
        {% endif %}
      </div>

      <section class="desktop-detail-workspace" aria-label="Detail workspace">
```

### 147. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_desktop_ops_workspace.html:269`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'forecast'. Use Next Load Estimate / Pickup Estimate / Timing Status instead.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
iver.new_driving_log') }}">Add first stop</a></div>
        </section>
      </div>
    </template>

    {% for stop in rm.stops|default([]) if rm %}
      {% set log = route_logs_by_id.get(stop.stop_id) %}
      {% set forecast = (stop_forecasts or {}).get(stop.stop_id) %}
      {% set stop_transfer = namespace(item=none) %}
      {% for transfer in route_transfers %}
        {% set from_text = (transfer.ship_from or '')|lower %}
```

### 148. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_desktop_ops_workspace.html:269`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'forecast'. Use Next Load Estimate / Pickup Estimate / Timing Status instead.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
log') }}">Add first stop</a></div>
        </section>
      </div>
    </template>

    {% for stop in rm.stops|default([]) if rm %}
      {% set log = route_logs_by_id.get(stop.stop_id) %}
      {% set forecast = (stop_forecasts or {}).get(stop.stop_id) %}
      {% set stop_transfer = namespace(item=none) %}
      {% for transfer in route_transfers %}
        {% set from_text = (transfer.ship_from or '')|lower %}
        {% set to_text
```

### 149. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_desktop_ops_workspace.html:309`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'forecast'. Use Next Load Estimate / Pickup Estimate / Timing Status instead.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
lse 'Arrival required' }}</strong></div>
            <div><span>Depart</span><strong>{{ stop.departure_at|to_12h_format if stop.departure_at else 'Pending' }}</strong></div>
            <div><span>Wait</span><strong>{{ (forecast.elapsed_label if forecast and forecast.elapsed_label else stop.wait_label) }}</strong></div>
          </div>
          <div class="desk-overview-loads" aria-label="Stop load state">
            <div><span>Arriv
```

### 150. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_desktop_ops_workspace.html:309`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'forecast'. Use Next Load Estimate / Pickup Estimate / Timing Status instead.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
/strong></div>
            <div><span>Depart</span><strong>{{ stop.departure_at|to_12h_format if stop.departure_at else 'Pending' }}</strong></div>
            <div><span>Wait</span><strong>{{ (forecast.elapsed_label if forecast and forecast.elapsed_label else stop.wait_label) }}</strong></div>
          </div>
          <div class="desk-overview-loads" aria-label="Stop load state">
            <div><span>Arrived with</span><strong>{{ '
```

### 151. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_desktop_ops_workspace.html:309`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'forecast'. Use Next Load Estimate / Pickup Estimate / Timing Status instead.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
>
            <div><span>Depart</span><strong>{{ stop.departure_at|to_12h_format if stop.departure_at else 'Pending' }}</strong></div>
            <div><span>Wait</span><strong>{{ (forecast.elapsed_label if forecast and forecast.elapsed_label else stop.wait_label) }}</strong></div>
          </div>
          <div class="desk-overview-loads" aria-label="Stop load state">
            <div><span>Arrived with</span><strong>{{ 'No load captu
```

### 152. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/edit_pretrip_entry.html:12`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'critical'. Only use when a real threshold or customer rule defines it.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
(ID: {{ pretrip.id }})</h1>

  <form method="POST" action="" enctype="multipart/form-data" class="md-glass md-glow p-3 pretrip-checklist" data-autosave="true" data-autosave-key="pretrip-entry-{{ pretrip.id }}">
    <!-- CRITICAL: ensures CSRF token is included -->
    {{ form.hidden_tag() }}

    <!-- 1) BASIC INFO -->
    <div class="row mb-3">
      <div class="col-md-4">
        {{ form.truck_number.label }}
        {{ form.truck_num
```

### 153. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:204`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'critical'. Only use when a real threshold or customer rule defines it.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
x; object-fit:cover; border-radius:6px; border:1px solid #fecaca; background:#fff; flex:0 0 42px; }
  .problem-label { color:#be123c; text-transform:uppercase; letter-spacing:.04em; font-size:.62rem; display:block; }
  .critical-list { display:grid; gap:8px; padding:12px 16px; max-height:min(72vh,720px); overflow-y:auto; overscroll-behavior:contain; }
  .critical-row { display:grid; grid-template-columns:minmax(120px,.8fr) minmax(150px,
```

### 154. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:205`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'critical'. Only use when a real threshold or customer rule defines it.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
t-transform:uppercase; letter-spacing:.04em; font-size:.62rem; display:block; }
  .critical-list { display:grid; gap:8px; padding:12px 16px; max-height:min(72vh,720px); overflow-y:auto; overscroll-behavior:contain; }
  .critical-row { display:grid; grid-template-columns:minmax(120px,.8fr) minmax(150px,1fr) minmax(0,2fr) auto; gap:10px; align-items:flex-start; border:1px solid #fee2e2; background:#fff7f7; border-radius:10px; padding:10px
```

### 155. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:206`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'critical'. Only use when a real threshold or customer rule defines it.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
) minmax(150px,1fr) minmax(0,2fr) auto; gap:10px; align-items:flex-start; border:1px solid #fee2e2; background:#fff7f7; border-radius:10px; padding:10px; color:#991b1b; text-decoration:none; min-height:max-content; }
  .critical-row:hover { background:#fff1f2; color:#991b1b; }
  .critical-type { font-size:.68rem; font-weight:900; text-transform:uppercase; letter-spacing:.06em; color:#be123c; }
  .critical-stop { font-size:.82rem; font-w
```

### 156. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:207`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'critical'. Only use when a real threshold or customer rule defines it.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
:flex-start; border:1px solid #fee2e2; background:#fff7f7; border-radius:10px; padding:10px; color:#991b1b; text-decoration:none; min-height:max-content; }
  .critical-row:hover { background:#fff1f2; color:#991b1b; }
  .critical-type { font-size:.68rem; font-weight:900; text-transform:uppercase; letter-spacing:.06em; color:#be123c; }
  .critical-stop { font-size:.82rem; font-weight:900; color:#0f172a; overflow-wrap:anywhere; }
  .critic
```

### 157. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:208`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'critical'. Only use when a real threshold or customer rule defines it.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
tion:none; min-height:max-content; }
  .critical-row:hover { background:#fff1f2; color:#991b1b; }
  .critical-type { font-size:.68rem; font-weight:900; text-transform:uppercase; letter-spacing:.06em; color:#be123c; }
  .critical-stop { font-size:.82rem; font-weight:900; color:#0f172a; overflow-wrap:anywhere; }
  .critical-issue { font-size:.78rem; font-weight:800; color:#991b1b; overflow-wrap:anywhere; line-height:1.35; }
  .exception-c
```

### 158. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:209`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'critical'. Only use when a real threshold or customer rule defines it.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
}
  .critical-type { font-size:.68rem; font-weight:900; text-transform:uppercase; letter-spacing:.06em; color:#be123c; }
  .critical-stop { font-size:.82rem; font-weight:900; color:#0f172a; overflow-wrap:anywhere; }
  .critical-issue { font-size:.78rem; font-weight:800; color:#991b1b; overflow-wrap:anywhere; line-height:1.35; }
  .exception-chip-list { display:flex; flex-wrap:wrap; gap:5px; max-width:100%; }
  .exception-chip { display
```

### 159. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:378`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'critical'. Only use when a real threshold or customer rule defines it.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
{ width:218px; flex-basis:218px; }
    .mc-nav a { padding:10px 11px; font-size:.8rem; }
  }
  @media (max-width:960px) {
    .mc-side { display:none; }
    .mc { display:block; }
    .mc-main { min-height:100vh; }
    .critical-row { grid-template-columns:1fr; }
    .kpi-row  { grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); }
    .mc-header { padding:13px 16px; flex-wrap:wrap; }
    .mc-body   { padding:14px 16px; }
    .mc-
```

### 160. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:391`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'critical'. Only use when a real threshold or customer rule defines it.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
}
  @media (max-width:560px) {
    .mc-header-r { width:100%; justify-content:stretch; }
    .mc-srch-wrap { flex:1 1 100%; }
    .btn-create { flex:1 1 auto; justify-content:center; }
    .kpi-row   { gap:10px; }
    .critical-list { max-height:none; overflow:visible; }
    .div-tabs { width:100%; overflow-x:auto; }
  }
</style>
<script>document.body.classList.add('mgr-active');</script>

{# ── MANAGE MODAL ── #}
<div class="mbdrop" i
```

### 161. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:848`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'critical'. Only use when a real threshold or customer rule defines it.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
ound" d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
            </svg>
            Needs Attention
          </h3>
          <span class="text-sm text-muted">{{ critical_exceptions|length }} issue{{ '' if critical_exceptions|length == 1 else 's' }} visible; scroll this panel for the full list</span>
        </div>
        <div class="critical-list">
          {% for item in crit
```

### 162. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:848`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'critical'. Only use when a real threshold or customer rule defines it.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
            </svg>
            Needs Attention
          </h3>
          <span class="text-sm text-muted">{{ critical_exceptions|length }} issue{{ '' if critical_exceptions|length == 1 else 's' }} visible; scroll this panel for the full list</span>
        </div>
        <div class="critical-list">
          {% for item in critical_exceptions %}
            <a class="cri
```

### 163. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:850`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'critical'. Only use when a real threshold or customer rule defines it.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
<span class="text-sm text-muted">{{ critical_exceptions|length }} issue{{ '' if critical_exceptions|length == 1 else 's' }} visible; scroll this panel for the full list</span>
        </div>
        <div class="critical-list">
          {% for item in critical_exceptions %}
            <a class="critical-row" href="{{ item.url }}">
              <span class="critical-type">{{ item.type }}</span>
              <span class="criti
```

### 164. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:851`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'critical'. Only use when a real threshold or customer rule defines it.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
>{{ critical_exceptions|length }} issue{{ '' if critical_exceptions|length == 1 else 's' }} visible; scroll this panel for the full list</span>
        </div>
        <div class="critical-list">
          {% for item in critical_exceptions %}
            <a class="critical-row" href="{{ item.url }}">
              <span class="critical-type">{{ item.type }}</span>
              <span class="critical-stop">{{ item.route_stop }}</span>
```

### 165. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:852`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'critical'. Only use when a real threshold or customer rule defines it.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
if critical_exceptions|length == 1 else 's' }} visible; scroll this panel for the full list</span>
        </div>
        <div class="critical-list">
          {% for item in critical_exceptions %}
            <a class="critical-row" href="{{ item.url }}">
              <span class="critical-type">{{ item.type }}</span>
              <span class="critical-stop">{{ item.route_stop }}</span>
              <span class="critical-issue">{{ i
```

### 166. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:853`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'critical'. Only use when a real threshold or customer rule defines it.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
his panel for the full list</span>
        </div>
        <div class="critical-list">
          {% for item in critical_exceptions %}
            <a class="critical-row" href="{{ item.url }}">
              <span class="critical-type">{{ item.type }}</span>
              <span class="critical-stop">{{ item.route_stop }}</span>
              <span class="critical-issue">{{ item.issue }}</span>
              {% if item.photo_url %}<img cl
```

### 167. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:854`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'critical'. Only use when a real threshold or customer rule defines it.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
ass="critical-list">
          {% for item in critical_exceptions %}
            <a class="critical-row" href="{{ item.url }}">
              <span class="critical-type">{{ item.type }}</span>
              <span class="critical-stop">{{ item.route_stop }}</span>
              <span class="critical-issue">{{ item.issue }}</span>
              {% if item.photo_url %}<img class="problem-thumb" src="{{ item.photo_url }}" alt="Proof photo">
```

### 168. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:855`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'critical'. Only use when a real threshold or customer rule defines it.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
<a class="critical-row" href="{{ item.url }}">
              <span class="critical-type">{{ item.type }}</span>
              <span class="critical-stop">{{ item.route_stop }}</span>
              <span class="critical-issue">{{ item.issue }}</span>
              {% if item.photo_url %}<img class="problem-thumb" src="{{ item.photo_url }}" alt="Proof photo">{% endif %}
            </a>
          {% else %}
            <div clas
```

### 169. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:915`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'critical'. Only use when a real threshold or customer rule defines it.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
lowupCasesPanel">
        <div class="panel-top">
          <h3>Grouped Management Cases</h3>
          <span class="text-sm text-muted">Related history only, not route evidence</span>
        </div>
        <div class="critical-list">
          {% for case in followup_cases %}
            <div class="critical-row">
              <span class="critical-type">{{ case.case_type|replace('_', ' ')|title }}</span>
              <span class="c
```

### 170. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:917`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'critical'. Only use when a real threshold or customer rule defines it.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
Cases</h3>
          <span class="text-sm text-muted">Related history only, not route evidence</span>
        </div>
        <div class="critical-list">
          {% for case in followup_cases %}
            <div class="critical-row">
              <span class="critical-type">{{ case.case_type|replace('_', ' ')|title }}</span>
              <span class="critical-stop">{{ case.title }}</span>
              <span class="critical-issue">{{
```

### 171. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:918`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'critical'. Only use when a real threshold or customer rule defines it.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
text-muted">Related history only, not route evidence</span>
        </div>
        <div class="critical-list">
          {% for case in followup_cases %}
            <div class="critical-row">
              <span class="critical-type">{{ case.case_type|replace('_', ' ')|title }}</span>
              <span class="critical-stop">{{ case.title }}</span>
              <span class="critical-issue">{{ case.summary }} {{ case.metrics|join('; '
```

### 172. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:919`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'critical'. Only use when a real threshold or customer rule defines it.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
"critical-list">
          {% for case in followup_cases %}
            <div class="critical-row">
              <span class="critical-type">{{ case.case_type|replace('_', ' ')|title }}</span>
              <span class="critical-stop">{{ case.title }}</span>
              <span class="critical-issue">{{ case.summary }} {{ case.metrics|join('; ') }}</span>
            </div>
          {% endfor %}
        </div>
      </div>
      {% end
```

### 173. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:920`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'critical'. Only use when a real threshold or customer rule defines it.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
<div class="critical-row">
              <span class="critical-type">{{ case.case_type|replace('_', ' ')|title }}</span>
              <span class="critical-stop">{{ case.title }}</span>
              <span class="critical-issue">{{ case.summary }} {{ case.metrics|join('; ') }}</span>
            </div>
          {% endfor %}
        </div>
      </div>
      {% endif %}

      {# Live route/stop panel #}
      <div class="panel {
```

### 174. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/new_pretrip.html:21`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'critical'. Only use when a real threshold or customer rule defines it.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
<h1 class="mb-3">New PreTrip Inspection</h1>

  <form method="POST" action="" enctype="multipart/form-data" class="md-glass md-glow p-3 pretrip-checklist" data-autosave="true" data-autosave-key="pretrip-new">
    <!-- CRITICAL: ensures CSRF token is included -->
    {{ form.hidden_tag() }}
    {% if form.errors %}
      <div class="alert alert-danger">
        <strong>PreTrip was not saved.</strong> Check the highlighted fields and tr
```

### 175. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/pretrip.html:21`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'critical'. Only use when a real threshold or customer rule defines it.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
<h1 class="mb-3">New PreTrip Inspection</h1>

  <form method="POST" action="" enctype="multipart/form-data" class="md-glass md-glow p-3 pretrip-checklist" data-autosave="true" data-autosave-key="pretrip-new">
    <!-- CRITICAL: ensures CSRF token is included -->
    {{ form.hidden_tag() }}

    <!-- 1) BASIC INFO -->
    <div class="row mb-3">
      <div class="col-md-4">
        {{ form.truck_number.label }}
        {{ form.truck_num
```

### 176. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/view_driver_log.html:62`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'critical'. Only use when a real threshold or customer rule defines it.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
; margin-bottom:5px; color:#075985 !important; font-size:.68rem !important; font-weight:950; text-transform:uppercase; letter-spacing:.05em; }
    .severity-label.review { color:#92400e !important; }
    .severity-label.critical { color:#991b1b !important; }
    .exception-subhead { margin:2px 0 0; color:#334155; font-size:.72rem; font-weight:900; text-transform:uppercase; letter-spacing:.06em; }
    .delay-item { background:#fffbeb; bo
```

### 177. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/view_driver_log.html:156`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'critical'. Only use when a real threshold or customer rule defines it.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
l>{% endif %}</div>
        <div class="readout-item"><span>Stops</span><strong>{{ management_narrative.completed_stop_count }} / {{ stop_count }} complete</strong></div>
        <div class="readout-item"><span>Review / Critical</span><strong>{{ management_narrative.needs_review_items|length }} review{% if management_narrative.needs_review_items|length != 1 %}s{% endif %}, {{ management_narrative.critical_exception_count }} critical</st
```

### 178. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/view_driver_log.html:156`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'critical'. Only use when a real threshold or customer rule defines it.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
div class="readout-item"><span>Review / Critical</span><strong>{{ management_narrative.needs_review_items|length }} review{% if management_narrative.needs_review_items|length != 1 %}s{% endif %}, {{ management_narrative.critical_exception_count }} critical</strong></div>
      </div>
      <div class="readout-body" style="display:block;">
        <p class="readout-summary">{{ management_narrative.summary_sentence }}</p>
      </div>
```

### 179. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/view_driver_log.html:156`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'critical'. Only use when a real threshold or customer rule defines it.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
an>Review / Critical</span><strong>{{ management_narrative.needs_review_items|length }} review{% if management_narrative.needs_review_items|length != 1 %}s{% endif %}, {{ management_narrative.critical_exception_count }} critical</strong></div>
      </div>
      <div class="readout-body" style="display:block;">
        <p class="readout-summary">{{ management_narrative.summary_sentence }}</p>
      </div>
    </div>

    {% if managemen
```

### 180. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/view_driver_log.html:202`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'critical'. Only use when a real threshold or customer rule defines it.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
issue_closeout.created_at.strftime('%b %d, %I:%M %p') }}{% endif %}.
          {{ issue_closeout.details or issue_closeout.summary }}
        </p>
      </div>
    </div>
    {% endif %}

    {% if management_narrative.critical_exception_items %}
    <div class="report-section">
      <div class="report-section-head red">Critical Exceptions</div>
      <div class="report-section-body">
        <div class="severity-list">
          {% f
```

### 181. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/view_driver_log.html:204`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'critical'. Only use when a real threshold or customer rule defines it.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
s or issue_closeout.summary }}
        </p>
      </div>
    </div>
    {% endif %}

    {% if management_narrative.critical_exception_items %}
    <div class="report-section">
      <div class="report-section-head red">Critical Exceptions</div>
      <div class="report-section-body">
        <div class="severity-list">
          {% for item in management_narrative.critical_exception_items %}
            <div class="severity-item">
```

### 182. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/view_driver_log.html:207`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'critical'. Only use when a real threshold or customer rule defines it.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
<div class="report-section">
      <div class="report-section-head red">Critical Exceptions</div>
      <div class="report-section-body">
        <div class="severity-list">
          {% for item in management_narrative.critical_exception_items %}
            <div class="severity-item">
              <strong class="severity-label critical">{{ item.severity }}</strong>
              <strong>{{ item.title }}</strong>
              <span>{
```

### 183. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/view_driver_log.html:209`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'critical'. Only use when a real threshold or customer rule defines it.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
ss="report-section-body">
        <div class="severity-list">
          {% for item in management_narrative.critical_exception_items %}
            <div class="severity-item">
              <strong class="severity-label critical">{{ item.severity }}</strong>
              <strong>{{ item.title }}</strong>
              <span>{{ item.text }}</span>
            </div>
          {% endfor %}
        </div>
      </div>
    </div>
    {% en
```

### 184. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/view_driver_log.html:454`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'critical'. Only use when a real threshold or customer rule defines it.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
isk' %}red{% else %}amber{% endif %}">Issue Review</div>
        <div class="report-section-body">
          <div class="severity-item">
            <strong class="severity-label {% if primary_issue.severity == 'risk' %}critical{% else %}review{% endif %}">{{ primary_issue.label }}</strong>
            <strong>{{ primary_issue.reason }}</strong>
          </div>
          <div class="detail-pairs">
            {% if ev.load or ev.droppe
```

### 185. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_production_flow_map.html:225`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'critical'. Only use when a real threshold or customer rule defines it.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
.ops-board-spatial .flow-chip:focus-visible { outline: 2px solid #e5e7eb; outline-offset: 2px; }
      .ops-board-spatial .flow-chip--blocked, .ops-board-spatial .flow-chip--needs_review, .ops-board-spatial .flow-chip--critical, .ops-board-spatial .flow-chip--high { border-color: #ef4444; }
      .ops-board-spatial .flow-chip--waiting { border-color: #f59e0b; }
      .ops-board-spatial .flow-chip--active, .ops-board-spatial .flow-chip-
```

### 186. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_production_flow_map.html:399`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'critical'. Only use when a real threshold or customer rule defines it.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
is-active,
      .production-flow--mobile .ops-board-spatial .flow-chip--blocked,
      .production-flow--mobile .ops-board-spatial .flow-chip--needs_review,
      .production-flow--mobile .ops-board-spatial .flow-chip--critical,
      .production-flow--mobile .ops-board-spatial .flow-chip--high,
      .production-flow--mobile .ops-board-spatial .flow-chip--waiting,
      .production-flow--mobile .ops-board-spatial .flow-chip--active,
```

### 187. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_production_flow_map.html:660`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'critical'. Only use when a real threshold or customer rule defines it.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
</style>

    {% set attention_ns = namespace(count=0) %}
    {% set attention_items = [] %}
    {% for item in pf.flow_items %}
      {% if attention_ns.count < 8 and item.status in ('blocked','waiting','needs_review','critical','high') %}
        {% set attention_ns.count = attention_ns.count + 1 %}
        {% set _ = attention_items.append(item) %}
      {% endif %}
    {% endfor %}
    {% set current_attention = attention_items[0] i
```

### 188. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_production_flow_map.html:736`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'critical'. Only use when a real threshold or customer rule defines it.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
Alerts</p>
            {% if attention_items %}
              {% for item in attention_items[:3] %}
                <div class="flow-alert-card flow-alert-card--{{ 'blocked' if item.status in ('blocked','needs_review','critical','high') else 'waiting' }}"
                     data-flow-open="item"
                     data-flow-id="{{ item.item_id }}"
                     data-flow-node-key="{{ item.item_type }}:{{ item.linked_route_st
```

### 189. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_production_flow_map.html:871`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'critical'. Only use when a real threshold or customer rule defines it.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
s">
                  {% for item in pf.flow_items[:14] %}
                    {% set badge_text = '' %}
                    {% set badge_class = '' %}
                    {% if item.status in ('blocked','needs_review','critical','high') %}{% set badge_text = 'BLOCKED' %}{% set badge_class = 'chip-badge chip-badge--blocked' %}
                    {% elif item.status == 'waiting' %}{% set badge_text = 'WAIT' %}{% set badge_class = 'chip-
```

### 190. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_production_flow_drawer.html:140`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'critical'. Only use when a real threshold or customer rule defines it.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
rovals are shown from the event ledger as they are appended.</div></li>
          <li class="{{ item.status }}"><div><strong>Exceptions</strong> &middot; {{ item.status_label if item.status in ('blocked','needs_review','critical','high') else 'No active stop exception' }}</div></li>
          <li><div><strong>Proof / Documents</strong> &middot; {% if item.linked_transfer_id %}Plant Transfer #{{ item.linked_transfer_id }}{% elif item.lin
```

### 191. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/driver_logs_print.html:219`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
DENTS</h2>
      {% set section_no.value = section_no.value + 1 %}
      <ul class="simple-list">
        {% for detail in damage_report_details %}<li>{{ detail }}</li>{% endfor %}
      </ul>
    {% endif %}

    {% if exception_notes %}
      <h2 class="section-title">{{ section_no.value }}. EXCEPTIONS</h2>
      {% set section_no.value = section_no.value + 1 %}
      <ul class="simple-list">
        {% for note in exception_notes %}<
```

### 192. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/driver_logs_print.html:220`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
l class="simple-list">
        {% for detail in damage_report_details %}<li>{{ detail }}</li>{% endfor %}
      </ul>
    {% endif %}

    {% if exception_notes %}
      <h2 class="section-title">{{ section_no.value }}. EXCEPTIONS</h2>
      {% set section_no.value = section_no.value + 1 %}
      <ul class="simple-list">
        {% for note in exception_notes %}<li>{{ note }}</li>{% endfor %}
      </ul>
    {% endif %}

    <h2 class="
```

### 193. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/driver_logs_print.html:223`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
ndif %}

    {% if exception_notes %}
      <h2 class="section-title">{{ section_no.value }}. EXCEPTIONS</h2>
      {% set section_no.value = section_no.value + 1 %}
      <ul class="simple-list">
        {% for note in exception_notes %}<li>{{ note }}</li>{% endfor %}
      </ul>
    {% endif %}

    <h2 class="section-title">{{ section_no.value }}. SIGNATURES</h2>
    <div class="signature-grid">
      <div>
        <div class="sig-la
```

### 194. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:210`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
123c; }
  .critical-stop { font-size:.82rem; font-weight:900; color:#0f172a; overflow-wrap:anywhere; }
  .critical-issue { font-size:.78rem; font-weight:800; color:#991b1b; overflow-wrap:anywhere; line-height:1.35; }
  .exception-chip-list { display:flex; flex-wrap:wrap; gap:5px; max-width:100%; }
  .exception-chip { display:inline-flex; align-items:center; gap:4px; padding:3px 7px; border-radius:999px; font-size:.64rem; font-weight:900
```

### 195. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:211`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
low-wrap:anywhere; }
  .critical-issue { font-size:.78rem; font-weight:800; color:#991b1b; overflow-wrap:anywhere; line-height:1.35; }
  .exception-chip-list { display:flex; flex-wrap:wrap; gap:5px; max-width:100%; }
  .exception-chip { display:inline-flex; align-items:center; gap:4px; padding:3px 7px; border-radius:999px; font-size:.64rem; font-weight:900; background:#fff7ed; color:#9a3412; border:1px solid #fed7aa; white-space:normal;
```

### 196. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:212`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
y:inline-flex; align-items:center; gap:4px; padding:3px 7px; border-radius:999px; font-size:.64rem; font-weight:900; background:#fff7ed; color:#9a3412; border:1px solid #fed7aa; white-space:normal; line-height:1.2; }
  .exception-chip.damage { background:#fff1f2; color:#be123c; border-color:#fecdd3; }
  .exception-chip.missing { background:#fef3c7; color:#92400e; border-color:#fde68a; }
  .exception-chip.truck { background:#eff6ff; colo
```

### 197. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:213`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
-size:.64rem; font-weight:900; background:#fff7ed; color:#9a3412; border:1px solid #fed7aa; white-space:normal; line-height:1.2; }
  .exception-chip.damage { background:#fff1f2; color:#be123c; border-color:#fecdd3; }
  .exception-chip.missing { background:#fef3c7; color:#92400e; border-color:#fde68a; }
  .exception-chip.truck { background:#eff6ff; color:#1d4ed8; border-color:#bfdbfe; }
  .exception-chip.photo { background:#eef2ff; color
```

### 198. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:214`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
7aa; white-space:normal; line-height:1.2; }
  .exception-chip.damage { background:#fff1f2; color:#be123c; border-color:#fecdd3; }
  .exception-chip.missing { background:#fef3c7; color:#92400e; border-color:#fde68a; }
  .exception-chip.truck { background:#eff6ff; color:#1d4ed8; border-color:#bfdbfe; }
  .exception-chip.photo { background:#eef2ff; color:#3730a3; border-color:#c7d2fe; }
  .exception-chip-thumb { width:22px; height:18px; ob
```

### 199. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:215`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
f1f2; color:#be123c; border-color:#fecdd3; }
  .exception-chip.missing { background:#fef3c7; color:#92400e; border-color:#fde68a; }
  .exception-chip.truck { background:#eff6ff; color:#1d4ed8; border-color:#bfdbfe; }
  .exception-chip.photo { background:#eef2ff; color:#3730a3; border-color:#c7d2fe; }
  .exception-chip-thumb { width:22px; height:18px; object-fit:cover; border-radius:4px; border:1px solid rgba(55,48,163,.25); margin-left:
```

### 200. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:216`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
fef3c7; color:#92400e; border-color:#fde68a; }
  .exception-chip.truck { background:#eff6ff; color:#1d4ed8; border-color:#bfdbfe; }
  .exception-chip.photo { background:#eef2ff; color:#3730a3; border-color:#c7d2fe; }
  .exception-chip-thumb { width:22px; height:18px; object-fit:cover; border-radius:4px; border:1px solid rgba(55,48,163,.25); margin-left:-2px; }
  @keyframes pulse-red { 70% { box-shadow:0 0 0 8px rgba(220,38,38,0); } 100%
```

### 201. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:848`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
            </svg>
            Needs Attention
          </h3>
          <span class="text-sm text-muted">{{ critical_exceptions|length }} issue{{ '' if critical_exceptions|length == 1 else 's' }} visible; scroll this panel for the full list</span>
        </div>
        <div class="critical-list">
          {% for item in critical_exce
```

### 202. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:848`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
            </svg>
            Needs Attention
          </h3>
          <span class="text-sm text-muted">{{ critical_exceptions|length }} issue{{ '' if critical_exceptions|length == 1 else 's' }} visible; scroll this panel for the full list</span>
        </div>
        <div class="critical-list">
          {% for item in critical_exceptions %}
            <a class="critical-row
```

### 203. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:851`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
cal_exceptions|length }} issue{{ '' if critical_exceptions|length == 1 else 's' }} visible; scroll this panel for the full list</span>
        </div>
        <div class="critical-list">
          {% for item in critical_exceptions %}
            <a class="critical-row" href="{{ item.url }}">
              <span class="critical-type">{{ item.type }}</span>
              <span class="critical-stop">{{ item.route_stop }}</span>
```

### 204. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:1007`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
<span class="timing-sub">No active wait</span>
                      {% endif %}
                    </div>
                  </td>
                  <td class="align-middle">
                    {% if row.exceptions %}
                      <div class="exception-chip-list">
                        {% for item in row.exceptions %}
                          <span class="exception-chip {% if 'Damage' in item.label %}damage{%
```

### 205. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:1008`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
wait</span>
                      {% endif %}
                    </div>
                  </td>
                  <td class="align-middle">
                    {% if row.exceptions %}
                      <div class="exception-chip-list">
                        {% for item in row.exceptions %}
                          <span class="exception-chip {% if 'Damage' in item.label %}damage{% elif 'Missing' in item.label %}missing{% elif '
```

### 206. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:1009`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
</div>
                  </td>
                  <td class="align-middle">
                    {% if row.exceptions %}
                      <div class="exception-chip-list">
                        {% for item in row.exceptions %}
                          <span class="exception-chip {% if 'Damage' in item.label %}damage{% elif 'Missing' in item.label %}missing{% elif 'Truck' in item.label %}truck{% elif 'Photo' in item.label %}photo
```

### 207. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:1010`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
d class="align-middle">
                    {% if row.exceptions %}
                      <div class="exception-chip-list">
                        {% for item in row.exceptions %}
                          <span class="exception-chip {% if 'Damage' in item.label %}damage{% elif 'Missing' in item.label %}missing{% elif 'Truck' in item.label %}truck{% elif 'Photo' in item.label %}photo{% endif %}" title="{{ item.detail }}">{% if item.pho
```

### 208. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_dashboard.html:1010`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
'Damage' in item.label %}damage{% elif 'Missing' in item.label %}missing{% elif 'Truck' in item.label %}truck{% elif 'Photo' in item.label %}photo{% endif %}" title="{{ item.detail }}">{% if item.photo_url %}<img class="exception-chip-thumb" src="{{ item.photo_url }}" alt="Photo proof">{% endif %}{{ item.label }}</span>
                        {% endfor %}
                      </div>
                    {% else %}
```

### 209. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/view_driver_log.html:63`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
t; font-size:.68rem !important; font-weight:950; text-transform:uppercase; letter-spacing:.05em; }
    .severity-label.review { color:#92400e !important; }
    .severity-label.critical { color:#991b1b !important; }
    .exception-subhead { margin:2px 0 0; color:#334155; font-size:.72rem; font-weight:900; text-transform:uppercase; letter-spacing:.06em; }
    .delay-item { background:#fffbeb; border:1px solid #fde68a; border-radius:8px; p
```

### 210. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/view_driver_log.html:156`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
="readout-item"><span>Review / Critical</span><strong>{{ management_narrative.needs_review_items|length }} review{% if management_narrative.needs_review_items|length != 1 %}s{% endif %}, {{ management_narrative.critical_exception_count }} critical</strong></div>
      </div>
      <div class="readout-body" style="display:block;">
        <p class="readout-summary">{{ management_narrative.summary_sentence }}</p>
      </div>
    </div>
```

### 211. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/view_driver_log.html:202`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
oseout.created_at.strftime('%b %d, %I:%M %p') }}{% endif %}.
          {{ issue_closeout.details or issue_closeout.summary }}
        </p>
      </div>
    </div>
    {% endif %}

    {% if management_narrative.critical_exception_items %}
    <div class="report-section">
      <div class="report-section-head red">Critical Exceptions</div>
      <div class="report-section-body">
        <div class="severity-list">
          {% for item i
```

### 212. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/view_driver_log.html:204`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
e_closeout.summary }}
        </p>
      </div>
    </div>
    {% endif %}

    {% if management_narrative.critical_exception_items %}
    <div class="report-section">
      <div class="report-section-head red">Critical Exceptions</div>
      <div class="report-section-body">
        <div class="severity-list">
          {% for item in management_narrative.critical_exception_items %}
            <div class="severity-item">
```

### 213. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/view_driver_log.html:207`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
s="report-section">
      <div class="report-section-head red">Critical Exceptions</div>
      <div class="report-section-body">
        <div class="severity-list">
          {% for item in management_narrative.critical_exception_items %}
            <div class="severity-item">
              <strong class="severity-label critical">{{ item.severity }}</strong>
              <strong>{{ item.title }}</strong>
              <span>{{ item.te
```

### 214. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/view_driver_log.html:238`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
}
            {% set r = (log_routes or {}).get(dl.id) %}
            {% set is_active_stop = management_narrative.current_activity and dl.id == management_narrative.current_activity.log_id %}
            {% set is_open_exception = management_narrative.open_stop_exception and not dl.depart_time %}
            <tr class="{% if dl.id == log.id %}current-stop {% endif %}{% if is_active_stop %}active-stop {% endif %}{% if is_open_exception
```

### 215. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/view_driver_log.html:238`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
.get(dl.id) %}
            {% set is_active_stop = management_narrative.current_activity and dl.id == management_narrative.current_activity.log_id %}
            {% set is_open_exception = management_narrative.open_stop_exception and not dl.depart_time %}
            <tr class="{% if dl.id == log.id %}current-stop {% endif %}{% if is_active_stop %}active-stop {% endif %}{% if is_open_exception %}open-stop{% endif %}">
              <td
```

### 216. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/view_driver_log.html:239`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
t is_open_exception = management_narrative.open_stop_exception and not dl.depart_time %}
            <tr class="{% if dl.id == log.id %}current-stop {% endif %}{% if is_active_stop %}active-stop {% endif %}{% if is_open_exception %}open-stop{% endif %}">
              <td style="font-weight:900;color:#475569;">
                {{ loop.index }}
                {% if dl.id == log.id %}<span class="current-stop-marker">selected</span>{% en
```

### 217. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/view_driver_log.html:243`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
{{ loop.index }}
                {% if dl.id == log.id %}<span class="current-stop-marker">selected</span>{% endif %}
                {% if is_active_stop %}<span class="active-stop-marker">active</span>{% elif is_open_exception %}<span class="open-stop-marker">needs departure</span>{% endif %}
              </td>
              <td>
                {% if r %}
                  <div class="rlt-route">{{ r.plant }}</div>
```

### 218. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/view_driver_log.html:318`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
nt_narrative.has_damage_reports %}
    <div class="report-section">
      <div class="report-section-head red">Damage / Delay</div>
      <div class="report-section-body">
        {% if delay_logs %}
          <p class="exception-subhead">Delay Events</p>
          {% for dl in delay_logs %}
          {% set delay_route = (log_routes or {}).get(dl.id) %}
          <div class="delay-item">
            <div class="plant">Stop #{{ day_log_
```

### 219. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/view_driver_log.html:333`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
%}
              {% if dl.downtime_reason %}Reason: {{ dl.downtime_reason }}{% endif %}
            </div>
          </div>
          {% endfor %}
        {% endif %}

        {% if damage_reports %}
          <p class="exception-subhead">Damage Reports</p>
          {% for dr in damage_reports %}
          <div class="damage-item">
            <div class="plant">{{ dr.plant_name }} - {{ dr.stage|title }} move <span style="font-weight:7
```

### 220. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/view_driver_log.html:369`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
>
          <p class="detail-pair"><span>Scan / Photo Proof</span><strong>{% if hot_part_proof.has_any_proof %}Recorded{% else %}No scan proof recorded{% endif %}</strong></p>
          <p class="detail-pair"><span>Open Exception</span><strong>{{ hot_part_proof.open_exception or 'None' }}</strong></p>
          <p class="detail-pair"><span>Last Event</span><strong>{{ hot_part_proof.last_event_timestamp|to_detroit_datetime if hot_part_pr
```

### 221. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/view_driver_log.html:369`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
Photo Proof</span><strong>{% if hot_part_proof.has_any_proof %}Recorded{% else %}No scan proof recorded{% endif %}</strong></p>
          <p class="detail-pair"><span>Open Exception</span><strong>{{ hot_part_proof.open_exception or 'None' }}</strong></p>
          <p class="detail-pair"><span>Last Event</span><strong>{{ hot_part_proof.last_event_timestamp|to_detroit_datetime if hot_part_proof.last_event_timestamp else 'No event yet' }}
```

### 222. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/welcome.html:54`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
ss="col-md-6">
                  <a class="portal-link" href="{{ url_for('manager.manager_dashboard') }}">
                    <strong>Manager Dispatch</strong>
                    <span>Live route view, driver filters, exceptions, follow-ups, and print review.</span>
                  </a>
                </div>
                <div class="col-md-6">
                  <a class="portal-link" href="{{ url_for('auth.login') }}?required_ro
```

### 223. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/driver_task_detail.html:70`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
eta">Hot Part: {{ hot_part_proof.hot_part_number }}</p>
        <p class="hot-proof-meta">Move Status: <span id="hotMoveStatus">{{ hot_part_proof.current_status }}</span></p>
      </div>
      {% if hot_part_proof.open_exception %}<strong class="plain-status warn">{{ hot_part_proof.open_exception }}</strong>{% endif %}
    </div>
    <div class="hot-scan-row">
      <input id="hotScanValue" autocomplete="off" inputmode="text" placehold
```

### 224. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/driver_task_detail.html:70`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
ass="hot-proof-meta">Move Status: <span id="hotMoveStatus">{{ hot_part_proof.current_status }}</span></p>
      </div>
      {% if hot_part_proof.open_exception %}<strong class="plain-status warn">{{ hot_part_proof.open_exception }}</strong>{% endif %}
    </div>
    <div class="hot-scan-row">
      <input id="hotScanValue" autocomplete="off" inputmode="text" placeholder="Scan or enter part label">
      <button type="button" class="hot
```

### 225. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/damage_evidence_packet.html:102`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
rong></div>
      </div>
    </div>

    <div class="packet-section">
      <h2>2. Description</h2>
      <div class="packet-copy">{{ report.description }}</div>
    </div>

    <div class="packet-section">
      <h2>3. Exceptions and Warnings</h2>
      {% if packet.warnings %}
        <ul class="warning-list">
          {% for warning in packet.warnings %}<li>{{ warning }}</li>{% endfor %}
        </ul>
      {% else %}
        <div c
```

### 226. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_review.html:27`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
t:space-between; gap:10px; align-items:center; }
  .review-panel-head h3 { margin:0; color:#0f172a; font-size:.95rem; font-weight:900; }
  .review-panel-head span { color:#64748b; font-size:.72rem; font-weight:800; }
  .exception-table { width:100%; border-collapse:collapse; min-width:820px; }
  .exception-table th { padding:10px 12px; background:#f8fafc; border-bottom:1px solid #e2e8f0; color:#64748b; font-size:.64rem; font-weight:900;
```

### 227. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_review.html:28`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
gin:0; color:#0f172a; font-size:.95rem; font-weight:900; }
  .review-panel-head span { color:#64748b; font-size:.72rem; font-weight:800; }
  .exception-table { width:100%; border-collapse:collapse; min-width:820px; }
  .exception-table th { padding:10px 12px; background:#f8fafc; border-bottom:1px solid #e2e8f0; color:#64748b; font-size:.64rem; font-weight:900; text-transform:uppercase; letter-spacing:.07em; text-align:left; }
  .excepti
```

### 228. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_review.html:29`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
; }
  .exception-table th { padding:10px 12px; background:#f8fafc; border-bottom:1px solid #e2e8f0; color:#64748b; font-size:.64rem; font-weight:900; text-transform:uppercase; letter-spacing:.07em; text-align:left; }
  .exception-table td { padding:11px 12px; border-bottom:1px solid #f1f5f9; vertical-align:middle; }
  .exception-table tr:last-child td { border-bottom:0; }
  .priority { display:inline-flex; padding:3px 8px; border-radius
```

### 229. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_review.html:30`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
olor:#64748b; font-size:.64rem; font-weight:900; text-transform:uppercase; letter-spacing:.07em; text-align:left; }
  .exception-table td { padding:11px 12px; border-bottom:1px solid #f1f5f9; vertical-align:middle; }
  .exception-table tr:last-child td { border-bottom:0; }
  .priority { display:inline-flex; padding:3px 8px; border-radius:999px; font-size:.66rem; font-weight:900; text-transform:uppercase; }
  .priority.high { background:
```

### 230. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_review.html:74`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
>
      <a href="{{ url_for('manager.audit_history') }}">Audit History</a>
    </nav>
  </aside>

  <main class="review-main">
    <header class="review-header">
      <div>
        <h2>Manager Review</h2>
        <p>{{ exceptions|length }} active exception{{ 's' if exceptions|length != 1 else '' }} this week</p>
      </div>
      <a class="btn btn-outline-secondary" href="{{ url_for('manager.audit_history') }}">Audit History</a>
    <
```

### 231. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_review.html:74`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
'manager.audit_history') }}">Audit History</a>
    </nav>
  </aside>

  <main class="review-main">
    <header class="review-header">
      <div>
        <h2>Manager Review</h2>
        <p>{{ exceptions|length }} active exception{{ 's' if exceptions|length != 1 else '' }} this week</p>
      </div>
      <a class="btn btn-outline-secondary" href="{{ url_for('manager.audit_history') }}">Audit History</a>
    </header>

    <div class="re
```

### 232. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_review.html:74`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
ory') }}">Audit History</a>
    </nav>
  </aside>

  <main class="review-main">
    <header class="review-header">
      <div>
        <h2>Manager Review</h2>
        <p>{{ exceptions|length }} active exception{{ 's' if exceptions|length != 1 else '' }} this week</p>
      </div>
      <a class="btn btn-outline-secondary" href="{{ url_for('manager.audit_history') }}">Audit History</a>
    </header>

    <div class="review-body">
      <
```

### 233. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_review.html:80`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
eek</p>
      </div>
      <a class="btn btn-outline-secondary" href="{{ url_for('manager.audit_history') }}">Audit History</a>
    </header>

    <div class="review-body">
      <section class="metric-grid" aria-label="Exception summary">
        <div class="metric"><span>Active Exceptions</span><strong>{{ metrics.active_count }}</strong></div>
        <div class="metric"><span>High Priority</span><strong>{{ metrics.high_count }}</stro
```

### 234. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_review.html:81`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
y" href="{{ url_for('manager.audit_history') }}">Audit History</a>
    </header>

    <div class="review-body">
      <section class="metric-grid" aria-label="Exception summary">
        <div class="metric"><span>Active Exceptions</span><strong>{{ metrics.active_count }}</strong></div>
        <div class="metric"><span>High Priority</span><strong>{{ metrics.high_count }}</strong></div>
        <div class="metric"><span>Truck / Damage</s
```

### 235. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_review.html:114`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
section class="review-panel">
        <div class="review-panel-head"><h3>Grouped Management Cases</h3><span>Related history, not route evidence</span></div>
        <div class="table-responsive">
          <table class="exception-table">
            <thead><tr><th>Case</th><th>Summary</th><th>Signals</th><th>Owner</th><th>Status</th></tr></thead>
            <tbody>
              {% for case in followup_cases %}
                <tr><td>
```

### 236. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_review.html:127`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
e.status }}</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </section>
      {% endif %}

      <section class="review-panel">
        <div class="review-panel-head"><h3>Exception Inbox</h3><span>View, resolve, or escalate from the row</span></div>
        <div class="table-responsive">
          <table class="exception-table">
            <thead><tr><th>Priority</th><th>Type</th><th>Rou
```

### 237. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_review.html:129`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
<section class="review-panel">
        <div class="review-panel-head"><h3>Exception Inbox</h3><span>View, resolve, or escalate from the row</span></div>
        <div class="table-responsive">
          <table class="exception-table">
            <thead><tr><th>Priority</th><th>Type</th><th>Route / Stop</th><th>Issue</th><th>Owner</th><th>Age</th><th></th></tr></thead>
            <tbody>
              {% for item in exceptions %}
```

### 238. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_review.html:132`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
<table class="exception-table">
            <thead><tr><th>Priority</th><th>Type</th><th>Route / Stop</th><th>Issue</th><th>Owner</th><th>Age</th><th></th></tr></thead>
            <tbody>
              {% for item in exceptions %}
                <tr>
                  <td><span class="priority {{ item.severity }}">{{ item.severity|title }}</span></td>
                  <td>{{ item.category }}</td>
                  <td><div class="i
```

### 239. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_review.html:143`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
ass="review-actions">
                      {% if item.url %}<a class="btn btn-sm btn-outline-primary" href="{{ item.url }}">View</a>{% endif %}
                      <form method="POST" action="{{ url_for('manager.mark_exception_reviewed') }}">
                        <input type="hidden" name="review_key" value="{{ item.review_key }}">
                        <input type="hidden" name="target_type" value="{{ item.target_type }}">
```

### 240. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_review.html:155`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
<details class="more-actions">
                        <summary class="btn btn-sm btn-outline-secondary">More</summary>
                        <form class="mt-1" method="POST" action="{{ url_for('manager.mark_exception_reviewed') }}">
                          <input type="hidden" name="review_key" value="{{ item.review_key }}">
                          <input type="hidden" name="target_type" value="{{ item.target_type }}">
```

### 241. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_review.html:169`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
</form>
                      </details>
                    </div>
                  </td>
                </tr>
              {% else %}
                <tr><td colspan="7" class="text-muted">No active exceptions.</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </section>

      <details class="foldout" id="add-followup">
        <summary>Add Follow-up</summary>
```

### 242. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_review.html:190`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
}</div>
            <div class="col-md-2 d-flex align-items-end">{{ form.submit(class="btn btn-primary w-100") }}</div>
          </form>
        </div>
      </details>

      <details class="foldout">
        <summary>Exception History</summary>
        <div class="foldout-body list-group list-group-flush">
          {% for event in exception_history %}
            <div class="list-group-item px-0">
              <div class="d-flex ju
```

### 243. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_review.html:192`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
v>
          </form>
        </div>
      </details>

      <details class="foldout">
        <summary>Exception History</summary>
        <div class="foldout-body list-group list-group-flush">
          {% for event in exception_history %}
            <div class="list-group-item px-0">
              <div class="d-flex justify-content-between gap-2"><strong>{{ event.title }}</strong><span class="badge text-bg-{{ 'danger' if event.action
```

### 244. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/manager_review.html:199`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
_at|to_detroit_datetime if event.created_at else '' }}</div>
              <div class="small">{{ event.details }}</div>
            </div>
          {% else %}
            <div class="text-muted">No completed or deleted exceptions yet.</div>
          {% endfor %}
        </div>
      </details>

      <details class="foldout">
        <summary>Damage Flags</summary>
        <div class="foldout-body damage-mini-list">
          {% for r
```

### 245. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_production_flow_map.html:38`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
color: #9ca3af; display: block; font-size: 0.65rem; margin-top: 6px; }
      .ops-board-spatial .flow-map-lane-card b { color: #fff; font-size: 1.1rem; margin-right: 4px; }
      .ops-board-spatial .flow-map-lane-card--exceptions { border-top-color: #ef4444; }
      .ops-board-spatial .flow-map-lane-card--manifested { border-top-color: #3b82f6; }
      .ops-board-spatial .flow-map-lane-card--in_transit { border-top-color: #38bdf8; }
```

### 246. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_production_flow_map.html:250`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
ter: drop-shadow(0 0 14px rgba(56,189,248,0.92)); }
      .ops-board-spatial .flow-edge--waiting { stroke: #f59e0b; opacity: 1; filter: drop-shadow(0 0 13px rgba(245,158,11,0.86)); }
      .ops-board-spatial .flow-edge--exception { stroke: #ef4444; opacity: 1; filter: drop-shadow(0 0 15px rgba(239,68,68,0.9)); }
      .ops-board-spatial .flow-edge--completed { stroke: #10b981; filter: drop-shadow(0 0 11px rgba(16,185,129,0.72)); }
```

### 247. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_production_flow_map.html:325`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
ion-node-card--secondary { width: 174px; height: 118px; }
      .production-flow--mobile .ops-board-spatial .route-step-chip[data-status="completed"] { display: none; }
      .production-flow--mobile .ops-board-spatial .exception-ticker { display: none; }
      .production-flow--mobile .ops-board-spatial .flow-object-layer { grid-template-columns: repeat(3, minmax(0, 1fr)); }
      .production-flow--mobile .ops-board-spatial .flow-drawe
```

### 248. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_production_flow_map.html:359`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
tial .flow-edge,
      .production-flow--mobile .ops-board-spatial .flow-edge--active,
      .production-flow--mobile .ops-board-spatial .flow-edge--waiting,
      .production-flow--mobile .ops-board-spatial .flow-edge--exception,
      .production-flow--mobile .ops-board-spatial .flow-edge--completed,
      .production-flow--mobile .ops-board-spatial .flow-edge--live {
        stroke: #d7dce4;
        filter: drop-shadow(0 0 13px rgba(
```

### 249. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_production_flow_map.html:522`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
{ display: block; }
      .ops-board-spatial .shadow-ledger-row .ledger-edge { color: #cbd5e1; }
      .ops-board-spatial .shadow-ledger-row .ledger-proof { color: #60a5fa; }
      .ops-board-spatial .shadow-ledger-row.exception { border-color: rgba(239,68,68,0.66); box-shadow: 0 0 18px rgba(239,68,68,0.12); }
      .ops-board-spatial .shadow-ledger-row.active { border-color: rgba(56,189,248,0.55); }
      .ops-board-spatial .shadow-le
```

### 250. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_production_flow_map.html:539`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
-top: 2px; }
      .ops-board-spatial .bottom-strip { background-color: #111827; border-top: 1px solid #1f2937; padding: 8px 12px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
      .ops-board-spatial .exception-ticker { font-size: 0.7rem; display: flex; gap: 8px; overflow-x: auto; white-space: nowrap; align-items: center; scrollbar-width: thin; padding-bottom: 4px; }
      .ops-board-spatial .exception-ticker > strong
```

### 251. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_production_flow_map.html:540`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
.ops-board-spatial .exception-ticker { font-size: 0.7rem; display: flex; gap: 8px; overflow-x: auto; white-space: nowrap; align-items: center; scrollbar-width: thin; padding-bottom: 4px; }
      .ops-board-spatial .exception-ticker > strong { color: #ef4444; text-transform: uppercase; font-size: 0.65rem; flex-shrink: 0; }
      .ops-board-spatial .exception-item { display: inline-flex; align-items: center; gap: 6px; padding: 3px 8p
```

### 252. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_production_flow_map.html:541`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
ems: center; scrollbar-width: thin; padding-bottom: 4px; }
      .ops-board-spatial .exception-ticker > strong { color: #ef4444; text-transform: uppercase; font-size: 0.65rem; flex-shrink: 0; }
      .ops-board-spatial .exception-item { display: inline-flex; align-items: center; gap: 6px; padding: 3px 8px; border-radius: 4px; cursor: pointer; color: #fff; transition: background-color 0.2s; background-color: rgba(239, 68, 68, 0.1); borde
```

### 253. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_production_flow_map.html:542`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
x 8px; border-radius: 4px; cursor: pointer; color: #fff; transition: background-color 0.2s; background-color: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); flex-shrink: 0; }
      .ops-board-spatial .exception-item:hover { background-color: rgba(239, 68, 68, 0.2); }
      .ops-board-spatial .exception-item--waiting { background-color: rgba(245,158,11,0.1); border-color: rgba(245,158,11,0.3); }
      .ops-board-spatia
```

### 254. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_production_flow_map.html:543`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
ackground-color: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); flex-shrink: 0; }
      .ops-board-spatial .exception-item:hover { background-color: rgba(239, 68, 68, 0.2); }
      .ops-board-spatial .exception-item--waiting { background-color: rgba(245,158,11,0.1); border-color: rgba(245,158,11,0.3); }
      .ops-board-spatial .exception-item--waiting:hover { background-color: rgba(245,158,11,0.22); }
      .ops-boar
```

### 255. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_production_flow_map.html:544`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
eption-item:hover { background-color: rgba(239, 68, 68, 0.2); }
      .ops-board-spatial .exception-item--waiting { background-color: rgba(245,158,11,0.1); border-color: rgba(245,158,11,0.3); }
      .ops-board-spatial .exception-item--waiting:hover { background-color: rgba(245,158,11,0.22); }
      .ops-board-spatial .exception-empty { color: #6b7280; font-size: 0.7rem; }
      .ops-board-spatial .flow-proof-status { display: flex; ali
```

### 256. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_production_flow_map.html:545`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
tem--waiting { background-color: rgba(245,158,11,0.1); border-color: rgba(245,158,11,0.3); }
      .ops-board-spatial .exception-item--waiting:hover { background-color: rgba(245,158,11,0.22); }
      .ops-board-spatial .exception-empty { color: #6b7280; font-size: 0.7rem; }
      .ops-board-spatial .flow-proof-status { display: flex; align-items: center; gap: 10px; font-size: 0.68rem; margin-top: 8px; padding-top: 8px; border-top: 1px s
```

### 257. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_production_flow_map.html:630`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
p-chip .step-action {
	        white-space: normal;
	        overflow: visible;
	        text-overflow: clip;
	        overflow-wrap: anywhere;
	      }
	      body.mgr-active .production-flow--admin .ops-board-spatial .exception-ticker {
	        white-space: normal;
	        overflow-x: visible;
	        flex-wrap: wrap;
	      }
	      body.mgr-active .production-flow--admin .ops-board-spatial .exception-item {
	        flex-shrink:
```

### 258. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_production_flow_map.html:635`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
uction-flow--admin .ops-board-spatial .exception-ticker {
	        white-space: normal;
	        overflow-x: visible;
	        flex-wrap: wrap;
	      }
	      body.mgr-active .production-flow--admin .ops-board-spatial .exception-item {
	        flex-shrink: 1;
	        min-width: 0;
	        white-space: normal;
	      }
	      @media (max-width: 900px) {
	        body.mgr-active .production-flow--admin .ops-board-spatial .ops-spatial-
```

### 259. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_production_flow_map.html:750`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
dfor %}
            {% else %}
              <div class="flow-alert-card flow-alert-card--quiet">
                <strong>No blocked flow</strong>
                Current records do not show a structured production-flow exception.
              </div>
            {% endif %}
          </div>

          <div class="flow-stream-section">
            <p class="flow-stream-title">Live Event Stream</p>
            <ul class="flow-event-strea
```

### 260. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_production_flow_map.html:781`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
rrow-live-{{ flow_mode }}" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto" markerUnits="strokeWidth"><polygon points="0 0, 7 3.5, 0 7" fill="#d7dce4"/></marker>
                  <marker id="ops-arrow-exception-{{ flow_mode }}" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto" markerUnits="strokeWidth"><polygon points="0 0, 7 3.5, 0 7" fill="#d7dce4"/></marker>
                  <mask id="flow-card-cu
```

### 261. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_production_flow_map.html:970`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
low-console-status>{% if latest_edge %}{{ latest_edge.source_key }} &rarr; {{ latest_edge.target_key }}{% elif current_attention %}{{ current_attention.next_action or current_attention.status_label }}{% else %}No active exception{% endif %}</strong>
                </div>
                <div class="flow-console-cell">
                  <span>Ledger Proof</span>
                  <strong data-flow-console-proof>{% if latest_edge %}FlowE
```

### 262. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_production_flow_map.html:1002`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
</b></li>
                    {% endfor %}
                  </ul>
                </div>
              </template>
            {% endfor %}
          </div>

          <div class="bottom-strip">
            <div class="exception-ticker" aria-label="Needs attention">
              {% if attention_items %}
                <strong>NEEDS ATTENTION:</strong>
                {% for item in attention_items %}
                  <span class="ex
```

### 263. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_production_flow_map.html:1006`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
="exception-ticker" aria-label="Needs attention">
              {% if attention_items %}
                <strong>NEEDS ATTENTION:</strong>
                {% for item in attention_items %}
                  <span class="exception-item exception-item--{{ 'waiting' if item.status == 'waiting' else 'blocked' }}"
                        data-flow-open="item"
                        data-flow-id="{{ item.item_id }}"
                        d
```

### 264. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_production_flow_map.html:1006`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
ker" aria-label="Needs attention">
              {% if attention_items %}
                <strong>NEEDS ATTENTION:</strong>
                {% for item in attention_items %}
                  <span class="exception-item exception-item--{{ 'waiting' if item.status == 'waiting' else 'blocked' }}"
                        data-flow-open="item"
                        data-flow-id="{{ item.item_id }}"
                        data-flow-node-k
```

### 265. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_production_flow_map.html:1017`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
item.label }} &middot; {{ (item.next_action or item.stage or item.status_label or '')|truncate(40,true,'') }}
                  </span>
                {% endfor %}
              {% else %}
                <span class="exception-empty">{{ pf.empty_states.needs_attention_empty if pf and pf.empty_states else 'No production-flow issues found for this date.' }}</span>
              {% endif %}
            </div>
            <div class="flo
```

### 266. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_production_flow_map.html:1039`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
',
              'staging': 'Staging',
              'load_build': 'Load Build',
              'manifested': 'Manifested',
              'in_transit': 'In Transit',
              'receiving': 'Receiving',
              'exceptions': 'Exception',
            } %}
            {% macro stage_pretty(raw) -%}
              {%- if raw and ':' in raw -%}
                {%- set kind, body = raw.split(':', 1) -%}
                {%- if kind ==
```

### 267. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_production_flow_map.html:1039`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
'staging': 'Staging',
              'load_build': 'Load Build',
              'manifested': 'Manifested',
              'in_transit': 'In Transit',
              'receiving': 'Receiving',
              'exceptions': 'Exception',
            } %}
            {% macro stage_pretty(raw) -%}
              {%- if raw and ':' in raw -%}
                {%- set kind, body = raw.split(':', 1) -%}
                {%- if kind == 'object' -%}{{
```

### 268. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_production_flow_map.html:1473`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
get = visualForEdge(edge, 'target');
        var d = edgePath(source, target);
        if (!d) return null;
        var path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        var status = edge.is_exception ? 'exception' : (edge.status || 'active');
        path.setAttribute('class', 'flow-edge flow-edge--' + status + (edge.is_live ? ' flow-edge--live' : '') + (animate ? ' flow-edge--new' : ''));
        path.setA
```

### 269. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_production_flow_map.html:1473`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
orEdge(edge, 'target');
        var d = edgePath(source, target);
        if (!d) return null;
        var path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        var status = edge.is_exception ? 'exception' : (edge.status || 'active');
        path.setAttribute('class', 'flow-edge flow-edge--' + status + (edge.is_live ? ' flow-edge--live' : '') + (animate ? ' flow-edge--new' : ''));
        path.setAttribute('d',
```

### 270. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_production_flow_map.html:1480`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
-event-id', edge.event_id || '');
        path.setAttribute('data-source-key', edge.source_key || '');
        path.setAttribute('data-target-key', edge.target_key || '');
        path.setAttribute('marker-end', edge.is_exception ? 'url(#ops-arrow-exception-{{ flow_mode }})' : 'url(#ops-arrow-live-{{ flow_mode }})');
        edgeGroup.appendChild(path);
        if (animate && typeof path.getTotalLength === 'function') {
          var le
```

### 271. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_production_flow_map.html:1480`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
'');
        path.setAttribute('data-source-key', edge.source_key || '');
        path.setAttribute('data-target-key', edge.target_key || '');
        path.setAttribute('marker-end', edge.is_exception ? 'url(#ops-arrow-exception-{{ flow_mode }})' : 'url(#ops-arrow-live-{{ flow_mode }})');
        edgeGroup.appendChild(path);
        if (animate && typeof path.getTotalLength === 'function') {
          var length = Math.ceil(path.getTot
```

### 272. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_production_flow_drawer.html:17`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
er_summary and pf.ledger_summary.event_count == 1 else 's' }}</dd></div>
        <div><dt>Open Manifests</dt><dd>{{ pf.ledger_summary.open_manifest_count if pf.ledger_summary else 0 }}</dd></div>
        <div><dt>Active Exceptions</dt><dd>{{ pf.ledger_summary.active_exception_count if pf.ledger_summary else 0 }}</dd></div>
      </dl>
    </div>
  {% endfor %}

  {% for node in pf.flow_nodes %}
    {% set profile = node.production_profi
```

### 273. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_production_flow_drawer.html:17`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
1 else 's' }}</dd></div>
        <div><dt>Open Manifests</dt><dd>{{ pf.ledger_summary.open_manifest_count if pf.ledger_summary else 0 }}</dd></div>
        <div><dt>Active Exceptions</dt><dd>{{ pf.ledger_summary.active_exception_count if pf.ledger_summary else 0 }}</dd></div>
      </dl>
    </div>
  {% endfor %}

  {% for node in pf.flow_nodes %}
    {% set profile = node.production_profile %}
    {% set display_name = node.label ~ ('
```

### 274. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_production_flow_drawer.html:140`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
eline</strong> &middot; Arrival{% if item.departure_at %}, departure{% endif %}, scans, and approvals are shown from the event ledger as they are appended.</div></li>
          <li class="{{ item.status }}"><div><strong>Exceptions</strong> &middot; {{ item.status_label if item.status in ('blocked','needs_review','critical','high') else 'No active stop exception' }}</div></li>
          <li><div><strong>Proof / Documents</strong> &middot
```

### 275. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_production_flow_drawer.html:140`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
as they are appended.</div></li>
          <li class="{{ item.status }}"><div><strong>Exceptions</strong> &middot; {{ item.status_label if item.status in ('blocked','needs_review','critical','high') else 'No active stop exception' }}</div></li>
          <li><div><strong>Proof / Documents</strong> &middot; {% if item.linked_transfer_id %}Plant Transfer #{{ item.linked_transfer_id }}{% elif item.linked_document_id %}Document #{{ item.lin
```

### 276. NEEDS REVIEW — forbidden wording audit

**Location:** `templates/partials/_compact_route_map.html:474`
**Expected:** Rejected/vague wording should not appear in active UI copy unless explicitly justified.
**Actual:** Found term: 'exception'. Vague unless tied to an exact issue/review workflow.
**Recommendation:** Replace with approved operational language or document why this historical term must remain.

```text
" data-depart-next="3" data-require-destination>Continue</button>
              </div>
            </section>
            <section class="depart-step" data-depart-step="3">
              <span class="depart-step-kicker">exception check</span>
              <h4>Any damage, issue, or proof note?</h4>
              <div class="depart-choice-grid">
                <button type="button" data-depart-choice data-field="cargo_override_reason" d
```

### 277. NEEDS REVIEW — route state/status audit

**Location:** `templates/partials/_production_flow_map.html:324`
**Expected:** Status words should be derived from state, not hardcoded decorative copy.
**Actual:** Potential hardcoded status text 'completed' found.
**Recommendation:** Confirm this copy is backed by real state and add it to the status allowlist if intentional.

```text
le .ops-board-spatial .production-node-card--secondary { width: 174px; height: 118px; }
      .production-flow--mobile .ops-board-spatial .route-step-chip[data-status="completed"] { display: none; }
      .production-flow--mobile .ops-board-spatial .exception-ticker { display: none; }
      .production-flow--mobile .op
```

### 278. NEEDS REVIEW — silent failure check

**Location:** `app/blueprints/auth/routes.py:44`
**Expected:** Failures should show visible user feedback and log safely server-side.
**Actual:** Exception redirects/returns without visible message or logging.
**Recommendation:** Add explicit error handling, logging, and flash/toast/UI error messages.

```text
"):
        key = "driver_user_id"
        required_role = "driver"
    else:
        return None
    uid = flask_session.get(key)
    if not uid:
        return None
    try:
        user = User.query.get(int(uid))
    except (TypeError, ValueError):
        return None
    if user and user.role == required_role:
        return user
    return None


def _redirect_authenticated_user():
    if current_user.role == "management":
```

### 279. NEEDS REVIEW — silent failure check

**Location:** `app/blueprints/driver/routes.py:643`
**Expected:** Failures should show visible user feedback and log safely server-side.
**Actual:** Exception redirects/returns without visible message or logging.
**Recommendation:** Add explicit error handling, logging, and flash/toast/UI error messages.

```text
return today_local_date


def _requested_mobile_route_date():
    date_str = request.args.get("date")
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None


def _mobile_route_date_options(driver_id, route_date, today_local_date):
    options = [
        {
            "label": "Today",
            "date": today_local_date,
```

### 280. NEEDS REVIEW — silent failure check

**Location:** `app/blueprints/driver/routes.py:1018`
**Expected:** Failures should show visible user feedback and log safely server-side.
**Actual:** Exception redirects/returns without visible message or logging.
**Recommendation:** Add explicit error handling, logging, and flash/toast/UI error messages.

```text
orm.fuel.data or form.maintenance.data) else None


def _local_dt_for_hhmm(log_date, hhmm):
    if not log_date or not hhmm:
        return None
    try:
        parsed_time = datetime.strptime(hhmm, "%H:%M").time()
    except ValueError:
        return None
    return pytz.timezone("America/Detroit").localize(datetime.combine(log_date, parsed_time))


def _arrival_local_dt_for_log(log):
    value = (getattr(log, "arrive_time", None) or
```

### 281. NEEDS REVIEW — silent failure check

**Location:** `app/blueprints/driver/routes.py:1997`
**Expected:** Failures should show visible user feedback and log safely server-side.
**Actual:** Exception redirects/returns without visible message or logging.
**Recommendation:** Add explicit error handling, logging, and flash/toast/UI error messages.

```text
lue:
            parsed = datetime.strptime(value, "%H:%M")
        elif value.isdigit() and len(value) in (3, 4):
            parsed = datetime.strptime(value.zfill(4), "%H%M")
        else:
            return None
    except ValueError:
        return None
    return parsed.strftime("%H:%M")


def _format_hhmm_12h(hhmm):
    if not hhmm:
        return ""
    try:
        return datetime.strptime(hhmm, "%H:%M").strftime("%I:%M%p").low
```

### 282. NEEDS REVIEW — silent failure check

**Location:** `app/blueprints/driver/routes.py:4092`
**Expected:** Failures should show visible user feedback and log safely server-side.
**Actual:** Exception redirects/returns without visible message or logging.
**Recommendation:** Add explicit error handling, logging, and flash/toast/UI error messages.

```text
request.get_json(silent=True) or request.form

    def payload_float(name):
        value = payload.get(name)
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    raw_value = payload.get("raw_value") or payload.get("value")
    try:
        event = save_part_scan(
            log=log,
            route=_driver_log_contex
```

### 283. NEEDS REVIEW — silent failure check

**Location:** `app/blueprints/manager/routes.py:1385`
**Expected:** Failures should show visible user feedback and log safely server-side.
**Actual:** Python exception swallowed with pass.
**Recommendation:** Add explicit error handling, logging, and flash/toast/UI error messages.

```text
", "%Y-%m-%d %H:%M"):
        try:
            stamp = pytz.utc.localize(datetime.strptime(raw, fmt))
            return stamp.astimezone(pytz.timezone("America/Detroit")).strftime("%I:%M%p").lower().lstrip("0")
        except ValueError:
            pass
    normalized = raw.lower().replace(" ", "")
    for fmt in ("%I:%M%p", "%I%M%p", "%H:%M", "%H%M"):
        try:
            return datetime.strptime(normalized, fmt).strftime("%I:%M%
```

### 284. NEEDS REVIEW — silent failure check

**Location:** `app/blueprints/manager/routes.py:1391`
**Expected:** Failures should show visible user feedback and log safely server-side.
**Actual:** Python exception swallowed with pass.
**Recommendation:** Add explicit error handling, logging, and flash/toast/UI error messages.

```text
ass
    normalized = raw.lower().replace(" ", "")
    for fmt in ("%I:%M%p", "%I%M%p", "%H:%M", "%H%M"):
        try:
            return datetime.strptime(normalized, fmt).strftime("%I:%M%p").lower().lstrip("0")
        except ValueError:
            pass
    return raw


def _manager_stop_complete_time(log):
    return _manager_time_label(getattr(log, "depart_time", None)) or _manager_time_label(getattr(log, "arrive_time", None))



de
```

### 285. NEEDS REVIEW — silent failure check

**Location:** `app/models/log.py:84`
**Expected:** Failures should show visible user feedback and log safely server-side.
**Actual:** Exception redirects/returns without visible message or logging.
**Recommendation:** Add explicit error handling, logging, and flash/toast/UI error messages.

```text
_root = current_app.config.get("DRIVER_LOG_PHOTO_UPLOAD_FOLDER", "uploads/driver_log_photos")
            upload_path = os.path.abspath(os.path.join(current_app.root_path, os.pardir, upload_root, self.filename))
        except RuntimeError:
            return False
        return os.path.isfile(upload_path)

    @property
    def resolved_document_type(self):
        """Document type code, falling back to the legacy source-encoded value
```

### 286. NEEDS REVIEW — silent failure check

**Location:** `app/services/simple_pdf.py:65`
**Expected:** Failures should show visible user feedback and log safely server-side.
**Actual:** Exception redirects/returns without visible message or logging.
**Recommendation:** Add explicit error handling, logging, and flash/toast/UI error messages.

```text
ng_data_url_to_rgb(data_url):
    if not data_url or not str(data_url).startswith("data:image/png;base64,"):
        return None
    try:
        png = base64.b64decode(str(data_url).split(",", 1)[1], validate=True)
    except (binascii.Error, ValueError):
        return None

    if not png.startswith(b"\x89PNG\r\n\x1a\n"):
        return None

    offset = 8
    width = height = bit_depth = color_type = compression = filter_method = i
```

### 287. NEEDS REVIEW — silent failure check

**Location:** `app/services/simple_pdf.py:104`
**Expected:** Failures should show visible user feedback and log safely server-side.
**Actual:** Exception redirects/returns without visible message or logging.
**Recommendation:** Add explicit error handling, logging, and flash/toast/UI error messages.

```text
compression != 0
        or filter_method != 0
        or interlace != 0
        or channels is None
        or not idat_parts
    ):
        return None

    try:
        raw = zlib.decompress(b"".join(idat_parts))
    except zlib.error:
        return None

    stride = width * channels
    rows = []
    pos = 0
    prev = bytearray(stride)
    for _ in range(height):
        if pos >= len(raw):
            return None
        filter_
```

### 288. NEEDS REVIEW — silent failure check

**Location:** `app/services/simple_pdf.py:281`
**Expected:** Failures should show visible user feedback and log safely server-side.
**Actual:** Exception redirects/returns without visible message or logging.
**Recommendation:** Add explicit error handling, logging, and flash/toast/UI error messages.

```text
w:.2f} 0 0 {h:.2f} {x:.2f} {y:.2f} cm /{name} Do Q")
        return True

    def image_file(self, path, x, y, w, h):
        try:
            with open(path, "rb") as fh:
                image_bytes = fh.read()
        except OSError:
            return False
        if image_bytes.startswith(b"\x89PNG"):
            data_url = "data:image/png;base64," + base64.b64encode(image_bytes).decode("ascii")
            return self.image_png_da
```

### 289. NEEDS REVIEW — silent failure check

**Location:** `app/services/load_state.py:308`
**Expected:** Failures should show visible user feedback and log safely server-side.
**Actual:** Python exception swallowed with pass.
**Recommendation:** Add explicit error handling, logging, and flash/toast/UI error messages.

```text
_time", ""))
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return UTC_TZ.localize(datetime.strptime(value, fmt)).astimezone(DETROIT_TZ)
        except ValueError:
            pass
    try:
        parsed_time = datetime.strptime(value, "%H:%M").time()
    except ValueError:
        return None
    if not getattr(log, "date", None):
        return None
    return
```

### 290. NEEDS REVIEW — silent failure check

**Location:** `app/services/load_state.py:312`
**Expected:** Failures should show visible user feedback and log safely server-side.
**Actual:** Exception redirects/returns without visible message or logging.
**Recommendation:** Add explicit error handling, logging, and flash/toast/UI error messages.

```text
try:
            return UTC_TZ.localize(datetime.strptime(value, fmt)).astimezone(DETROIT_TZ)
        except ValueError:
            pass
    try:
        parsed_time = datetime.strptime(value, "%H:%M").time()
    except ValueError:
        return None
    if not getattr(log, "date", None):
        return None
    return DETROIT_TZ.localize(datetime.combine(log.date, parsed_time))


def _depart_local_datetime(log):
    value = _cl
```

### 291. NEEDS REVIEW — silent failure check

**Location:** `app/services/load_state.py:325`
**Expected:** Failures should show visible user feedback and log safely server-side.
**Actual:** Exception redirects/returns without visible message or logging.
**Recommendation:** Add explicit error handling, logging, and flash/toast/UI error messages.

```text
ocal_datetime(log):
    value = _clean(getattr(log, "depart_time", ""))
    if not value or not getattr(log, "date", None):
        return None
    try:
        parsed_time = datetime.strptime(value, "%H:%M").time()
    except ValueError:
        return None
    return DETROIT_TZ.localize(datetime.combine(log.date, parsed_time))


def _state(primary_destination=None, secondary_destination=None, secondary_value=None):
    primary_value =
```

### 292. NEEDS REVIEW — silent failure check

**Location:** `app/services/driver_wait.py:23`
**Expected:** Failures should show visible user feedback and log safely server-side.
**Actual:** Python exception swallowed with pass.
**Recommendation:** Add explicit error handling, logging, and flash/toast/UI error messages.

```text
(log, "arrive_time", None) or "").strip()
    if not value:
        return None
    for fmt in UTC_FORMATS:
        try:
            return pytz.utc.localize(datetime.strptime(value, fmt)).astimezone(DETROIT_TZ)
        except ValueError:
            pass
    try:
        parsed_time = datetime.strptime(value, "%H:%M").time()
    except ValueError:
        return None
    if not getattr(log, "date", None):
        return None
    return
```

### 293. NEEDS REVIEW — silent failure check

**Location:** `app/services/driver_wait.py:27`
**Expected:** Failures should show visible user feedback and log safely server-side.
**Actual:** Exception redirects/returns without visible message or logging.
**Recommendation:** Add explicit error handling, logging, and flash/toast/UI error messages.

```text
try:
            return pytz.utc.localize(datetime.strptime(value, fmt)).astimezone(DETROIT_TZ)
        except ValueError:
            pass
    try:
        parsed_time = datetime.strptime(value, "%H:%M").time()
    except ValueError:
        return None
    if not getattr(log, "date", None):
        return None
    return DETROIT_TZ.localize(datetime.combine(log.date, parsed_time))


def elapsed_wait_seconds(log, now=None):
    arr
```

### 294. NEEDS REVIEW — silent failure check

**Location:** `app/services/issue_severity.py:193`
**Expected:** Failures should show visible user feedback and log safely server-side.
**Actual:** Exception redirects/returns without visible message or logging.
**Recommendation:** Add explicit error handling, logging, and flash/toast/UI error messages.

```text
Critical.

    Returns ``None`` when ``minutes`` is missing/non-numeric so callers can
    skip rendering a badge entirely.
    """
    if minutes is None:
        return None
    try:
        minutes = int(minutes)
    except (TypeError, ValueError):
        return None
    limit = threshold if threshold else DEFAULT_WAIT_THRESHOLD
    if minutes >= limit:
        level = "action"
    elif minutes >= 10:
        level = "watch"
    els
```

### 295. NEEDS REVIEW — silent failure check

**Location:** `app/services/production_flow.py:342`
**Expected:** Failures should show visible user feedback and log safely server-side.
**Actual:** Exception redirects/returns without visible message or logging.
**Recommendation:** Add explicit error handling, logging, and flash/toast/UI error messages.

```text
if value_date == target:
            return True
    return False


def _safe_url(endpoint, **values):
    if not has_request_context():
        return None
    try:
        return url_for(endpoint, **values)
    except (BuildError, RuntimeError):
        return None


def _location_label(value):
    text = _clean(value)
    if not text:
        return None
    text_key = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    co
```

### 296. NEEDS REVIEW — silent failure check

**Location:** `app/services/route_map.py:85`
**Expected:** Failures should show visible user feedback and log safely server-side.
**Actual:** Exception redirects/returns without visible message or logging.
**Recommendation:** Add explicit error handling, logging, and flash/toast/UI error messages.

```text
replace(tzinfo=None)
    return utc_start, utc_start + timedelta(days=1)


def _safe_url(endpoint, **values):
    if not has_request_context():
        return None
    try:
        return url_for(endpoint, **values)
    except (BuildError, RuntimeError):
        return None


def _date_param(value):
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date_cls):
        return value.isofor
```

### 297. NEEDS REVIEW — silent failure check

**Location:** `app/services/constraint_engine.py:39`
**Expected:** Failures should show visible user feedback and log safely server-side.
**Actual:** Exception redirects/returns without visible message or logging.
**Recommendation:** Add explicit error handling, logging, and flash/toast/UI error messages.

```text
.

    PartRouteProfile (app/models/part.py) carries any per-SKU equipment
    restriction. Falls back to no restriction when the table is empty.
    """
    try:
        from app.models.part import PartRouteProfile
    except Exception:
        return None
    if not skus:
        return None
    profiles = PartRouteProfile.query.filter(PartRouteProfile.part_sku.in_(skus)).all()
    required = set()
    for profile in profiles:
```

### 298. NEEDS REVIEW — silent failure check

**Location:** `templates/pretrip_printable.html:450`
**Expected:** Failures should show visible user feedback and log safely server-side.
**Actual:** fetch call may lack error handling.
**Recommendation:** Add explicit error handling, logging, and flash/toast/UI error messages.

```text
nt_user.display_name if current_user else "" }}<br>
    <strong>Reviewing Driver:</strong> ________ (Emp. No: ____) Date: ________
  </div>
</main>
<script>
  async function markPrintedAndPrint() {
    try {
      await fetch("{{ url_for(pretrip_mark_endpoint, pretrip_id=pretrip.id) }}", {
        method: "POST",
        credentials: "same-origin"
      });
    } catch (err) {
      console.error("Could not record print activity:", err)
```

### 299. NEEDS REVIEW — silent failure check

**Location:** `templates/plant_transfer_printable.html:133`
**Expected:** Failures should show visible user feedback and log safely server-side.
**Actual:** fetch call may lack error handling.
**Recommendation:** Add explicit error handling, logging, and flash/toast/UI error messages.

```text
C - Plant Transfer &nbsp; | &nbsp; Ret: 1 mo. after the mo. of creation &nbsp; | &nbsp; Effective Date: 1/1/10</div>
    </section>
  {% endfor %}

<script>
  async function markPrintedAndPrint() {
    try {
      await fetch("{{ url_for(transfer_mark_endpoint, transfer_id=transfer.id, copy=requested_copy) }}", {
        method: "POST",
        credentials: "same-origin"
      });
    } catch (err) {
      console.error('Could not recor
```

### 300. NEEDS REVIEW — printout wording/layout audit

**Location:** `app/services/simple_pdf.py:188`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'dev'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
(">H", jpeg_bytes[pos + 5 : pos + 7])[0]
            components = jpeg_bytes[pos + 7] if pos + 7 < len(jpeg_bytes) else 3
            if width and height and components in {1, 3}:
                return width, height, "/DeviceGray" if components == 1 else "/DeviceRGB"
            return None
        pos += segment_len
    return None


def _image_dimensions(image_bytes):
    """Return (width, height) in pixels for a PNG or baseline JPEG
```

### 301. NEEDS REVIEW — printout wording/layout audit

**Location:** `app/services/simple_pdf.py:188`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'dev'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
0]
            components = jpeg_bytes[pos + 7] if pos + 7 < len(jpeg_bytes) else 3
            if width and height and components in {1, 3}:
                return width, height, "/DeviceGray" if components == 1 else "/DeviceRGB"
            return None
        pos += segment_len
    return None


def _image_dimensions(image_bytes):
    """Return (width, height) in pixels for a PNG or baseline JPEG, else None."""
    if image_bytes[:8]
```

### 302. NEEDS REVIEW — printout wording/layout audit

**Location:** `app/services/simple_pdf.py:269`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'dev'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
name = f"Im{len(self.images) + 1}"
        self.images.append(
            {
                "name": name,
                "width": image_width,
                "height": image_height,
                "color_space": "/DeviceRGB",
                "filter": "/FlateDecode",
                "stream": zlib.compress(rgb_bytes),
            }
        )
        self.current.append(f"q {w:.2f} 0 0 {h:.2f} {x:.2f} {y:.2f} cm /{name} Do Q")
```

### 303. NEEDS REVIEW — printout wording/layout audit

**Location:** `app/services/simple_pdf.py:367`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'dev'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
e["stream"].decode("latin-1")
            objects.append(
                f"<< /Type /XObject /Subtype /Image /Width {image['width']} "
                f"/Height {image['height']} /ColorSpace {image.get('color_space', '/DeviceRGB')} /BitsPerComponent 8 "
                f"/Filter {image.get('filter', '/FlateDecode')} /Length {len(image['stream'])} >>\n"
                f"stream\n{stream}\nendstream"
            )
        xobject_resourc
```

### 304. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/driver_logs_print.html:98`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'click'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
ummary = route_sheet_summary|default({'total_stops': logs|length if logs else 0, 'open_stops': 0, 'total_miles': none, 'total_wait_minutes': 0}) %}
  <div class="print-controls no-print">
    <button class="print-btn" onclick="window.print()">Print Document</button>
    <a class="email-btn" href="{{ url_for('driver.driver_logs_print', date=the_date.isoformat(), autoprint=1) }}">Save PDF</a>
    {% if csv_url is defined %}<a class="email
```

### 305. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/driver_logs_print.html:84`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
4in; margin-top: 3px; font-size: 7pt; color: #555; }
    @media screen { body { padding: 1rem; } }
    @media print {
      body { padding: 0; }
      .no-print, .screen-only, .print-controls, .helper-text, .form-hint, .button-row, nav, header.app-nav, .print-btn, .email-btn { display: none !important; }
      th { background: #eee !important; }
      * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    }
  </style>
<
```

### 306. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/driver_logs_print.html:98`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
_date else '' %}
  {% set summary = route_sheet_summary|default({'total_stops': logs|length if logs else 0, 'open_stops': 0, 'total_miles': none, 'total_wait_minutes': 0}) %}
  <div class="print-controls no-print">
    <button class="print-btn" onclick="window.print()">Print Document</button>
    <a class="email-btn" href="{{ url_for('driver.driver_logs_print', date=the_date.isoformat(), autoprint=1) }}">Save PDF</a>
    {% if csv_url i
```

### 307. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/driver_logs_print.html:98`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
total_stops': logs|length if logs else 0, 'open_stops': 0, 'total_miles': none, 'total_wait_minutes': 0}) %}
  <div class="print-controls no-print">
    <button class="print-btn" onclick="window.print()">Print Document</button>
    <a class="email-btn" href="{{ url_for('driver.driver_logs_print', date=the_date.isoformat(), autoprint=1) }}">Save PDF</a>
    {% if csv_url is defined %}<a class="email-btn" href="{{ csv_url }}">CSV Export</
```

### 308. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/driver_logs_print.html:256`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'dev'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
label">Manager / Reviewer Signature</div>
        <div class="sig-line"></div>
        <div class="sig-ts">&nbsp;</div>
      </div>
    </div>
  </main>
</div>
{% if request.args.get('autoprint') %}
<script>
  window.addEventListener("load", function () {
    window.setTimeout(function () {
      window.print();
    }, 150);
  });
</script>
{% endif %}
</body>
</html>
```

### 309. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/end_of_day_print.html:169`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'click'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
et document_meta = document_meta|default({'title': 'END OF DAY ROUTE RECORD', 'document_no': 'EOD-' ~ the_date, 'generated_at': '', 'page': '1 of 1'}) %}
<div class="print-controls no-print">
<button class="print-btn" onclick="window.print()">Print Document</button>
  <a class="email-btn" href="{{ url_for('driver.end_of_day_print', autoprint=1) }}">Save PDF</a>
</div>

<main class="print-container official-print-document">
  <header cla
```

### 310. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/end_of_day_print.html:142`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
width: auto;
        padding: 0;
      }
      .print-guidance {
      margin: 0 0 0.12in;
      color: #444;
      font-size: 9pt;
    }
    .no-print, .screen-only, .print-controls, .helper-text, .form-hint, .button-row, nav, header.app-nav, .print-btn, .email-btn, .print-guidance {
        display: none !important;
      }
      .no-print, .screen-only { }
    .print-controls { margin-bottom:0.12in; }
    .document-header {
```

### 311. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/end_of_day_print.html:169`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
style>
</head>
<body>

{% set document_meta = document_meta|default({'title': 'END OF DAY ROUTE RECORD', 'document_no': 'EOD-' ~ the_date, 'generated_at': '', 'page': '1 of 1'}) %}
<div class="print-controls no-print">
<button class="print-btn" onclick="window.print()">Print Document</button>
  <a class="email-btn" href="{{ url_for('driver.end_of_day_print', autoprint=1) }}">Save PDF</a>
</div>

<main class="print-container official-pri
```

### 312. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/end_of_day_print.html:169`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
t({'title': 'END OF DAY ROUTE RECORD', 'document_no': 'EOD-' ~ the_date, 'generated_at': '', 'page': '1 of 1'}) %}
<div class="print-controls no-print">
<button class="print-btn" onclick="window.print()">Print Document</button>
  <a class="email-btn" href="{{ url_for('driver.end_of_day_print', autoprint=1) }}">Save PDF</a>
</div>

<main class="print-container official-print-document">
  <header class="document-header print-only">
    <d
```

### 313. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/end_of_day_print.html:311`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'dev'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
<div class="sig-label">Manager / Auditor Signature</div>
      <div class="sig-line"></div>
      <div class="sig-ts">&nbsp;</div>
    </div>
  </div>
</main>

{% if request.args.get('autoprint') %}
<script>
  window.addEventListener("load", function () {
    window.setTimeout(function () {
      window.print();
    }, 150);
  });
</script>
{% endif %}
</body>
</html>
```

### 314. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/pdf_daily_logs.html`
**Expected:** Audit printouts should use numbered sections or a clear ordered structure.
**Actual:** No obvious section numbering found in print-related file.
**Recommendation:** Number print sections and add a screenshot/PDF baseline.

### 315. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/pretrip_printable.html:238`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'click'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
{% if can_edit_pretrip %}
      <a class="edit-btn" href="{{ url_for('driver.edit_pretrip_entry', pretrip_id=pretrip.id) }}">Edit PreTrip Before Printing</a>
    {% endif %}
    <button class="print-btn" type="button" onclick="{% if can_mark_printed %}markPrintedAndPrint(){% else %}window.print(){% endif %}">Print Document</button>
    <a class="email-btn" href="{{ url_for(pretrip_attachment_endpoint, pretrip_id=pretrip.id) }}">Save PDF
```

### 316. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/pretrip_printable.html:194`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
dding: 0;
      }
      .print-guidance {
      margin: 0 0 0.12in;
      color: #444;
      font-size: 9pt;
    }
      .no-print,
      .screen-only,
      .print-controls,
      .helper-text,
      .form-hint,
      .button-row,
      nav,
      header.app-nav,
      .print-actions,
      .print-btn,
      .edit-btn,
      .email-btn,
      .back-btn {
        display: none !important;
      }
      .print-container {
        width:
```

### 317. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/pretrip_printable.html:238`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
rint">
  <div class="print-actions">
    {% if can_edit_pretrip %}
      <a class="edit-btn" href="{{ url_for('driver.edit_pretrip_entry', pretrip_id=pretrip.id) }}">Edit PreTrip Before Printing</a>
    {% endif %}
    <button class="print-btn" type="button" onclick="{% if can_mark_printed %}markPrintedAndPrint(){% else %}window.print(){% endif %}">Print Document</button>
    <a class="email-btn" href="{{ url_for(pretrip_attachment_endp
```

### 318. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/pretrip_printable.html:238`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
ons">
    {% if can_edit_pretrip %}
      <a class="edit-btn" href="{{ url_for('driver.edit_pretrip_entry', pretrip_id=pretrip.id) }}">Edit PreTrip Before Printing</a>
    {% endif %}
    <button class="print-btn" type="button" onclick="{% if can_mark_printed %}markPrintedAndPrint(){% else %}window.print(){% endif %}">Print Document</button>
    <a class="email-btn" href="{{ url_for(pretrip_attachment_endpoint, pretrip_id=pretrip.id) }}
```

### 319. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/pretrip_printable.html:238`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
id=pretrip.id) }}">Edit PreTrip Before Printing</a>
    {% endif %}
    <button class="print-btn" type="button" onclick="{% if can_mark_printed %}markPrintedAndPrint(){% else %}window.print(){% endif %}">Print Document</button>
    <a class="email-btn" href="{{ url_for(pretrip_attachment_endpoint, pretrip_id=pretrip.id) }}">Save PDF</a>
    <a class="back-btn" href="{{ back_url }}">Back to Inspections</a>
  </div>
</div>

<main class="p
```

### 320. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/pretrip_printable.html:460`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'dev'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
d: "POST",
        credentials: "same-origin"
      });
    } catch (err) {
      console.error("Could not record print activity:", err);
    }
    window.print();
  }
  {% if request.args.get('autoprint') %}
  window.addEventListener("load", function () {
    window.setTimeout(function () {
      {% if can_mark_printed %}markPrintedAndPrint();{% else %}window.print();{% endif %}
    }, 150);
  });
  {% endif %}
</script>
</body>
</html
```

### 321. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/view_driver_log.html:136`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'click'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
mb-0">{% if current_user.role == 'management' %}MOVEDEFENSE — ROUTE AUDIT{% else %}View Driver Log{% endif %}</h2>
    {% if current_user.role == 'management' %}<button type="button" class="btn btn-outline-secondary" onclick="window.print()">Print Management Copy</button>{% endif %}
  </div>

  {% if current_user.role == 'management' %}
    <div class="management-readout">
      <div class="readout-header">
        <p class="readout-ey
```

### 322. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/view_driver_log.html:51`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
t:800; }
    .driver-issue-actions { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:10px; }
    .driver-issue-actions form { margin:0; }
    .driver-issue-actions .btn, .driver-issue-actions button { width:100%; }
    .driver-issue-closeout { grid-column:1 / -1; display:grid; gap:8px; padding:10px; border:1px solid #fde68a; border-radius:8px; background:#fffbeb; }
    .driver-issue-closeout label { margin:0;
```

### 323. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/view_driver_log.html:136`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
n align-items-center gap-2 no-print">
    <h2 class="mt-3 mb-0">{% if current_user.role == 'management' %}MOVEDEFENSE — ROUTE AUDIT{% else %}View Driver Log{% endif %}</h2>
    {% if current_user.role == 'management' %}<button type="button" class="btn btn-outline-secondary" onclick="window.print()">Print Management Copy</button>{% endif %}
  </div>

  {% if current_user.role == 'management' %}
    <div class="management-readout">
```

### 324. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/view_driver_log.html:136`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
-center gap-2 no-print">
    <h2 class="mt-3 mb-0">{% if current_user.role == 'management' %}MOVEDEFENSE — ROUTE AUDIT{% else %}View Driver Log{% endif %}</h2>
    {% if current_user.role == 'management' %}<button type="button" class="btn btn-outline-secondary" onclick="window.print()">Print Management Copy</button>{% endif %}
  </div>

  {% if current_user.role == 'management' %}
    <div class="management-readout">
      <div class="r
```

### 325. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/view_driver_log.html:136`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
%}MOVEDEFENSE — ROUTE AUDIT{% else %}View Driver Log{% endif %}</h2>
    {% if current_user.role == 'management' %}<button type="button" class="btn btn-outline-secondary" onclick="window.print()">Print Management Copy</button>{% endif %}
  </div>

  {% if current_user.role == 'management' %}
    <div class="management-readout">
      <div class="readout-header">
        <p class="readout-eyebrow">Route Summary</p>
      </div>
      <d
```

### 326. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/view_driver_log.html:303`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
{ url_for(photo_delete_endpoint, photo_id=photo.id) }}" onsubmit="return confirm('Delete this stop photo proof?');">
                  <input type="hidden" name="next" value="{{ request.full_path }}">
                  <button class="proof-photo-delete" type="submit">Remove Photo</button>
                </form>
              {% endif %}
            </div>
          {% endfor %}
        </div>
      </div>
    </div>
    {% endif %}
```

### 327. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/view_driver_log.html:303`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
it="return confirm('Delete this stop photo proof?');">
                  <input type="hidden" name="next" value="{{ request.full_path }}">
                  <button class="proof-photo-delete" type="submit">Remove Photo</button>
                </form>
              {% endif %}
            </div>
          {% endfor %}
        </div>
      </div>
    </div>
    {% endif %}

    {% if management_narrative.has_delay_events or management_na
```

### 328. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/view_driver_log.html:474`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
ason">Closeout reason required</label>
              <textarea id="issueCloseoutReason" name="reason" required placeholder="Tell the manager why this can be closed and the route can continue."></textarea>
              <button class="btn btn-success" type="submit">{{ closeout_label }}</button>
            </form>
            {% if primary_issue.code == 'destination_mismatch' %}
              <a class="btn btn-warning" href="{{ url_for('
```

### 329. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/view_driver_log.html:474`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
issueCloseoutReason" name="reason" required placeholder="Tell the manager why this can be closed and the route can continue."></textarea>
              <button class="btn btn-success" type="submit">{{ closeout_label }}</button>
            </form>
            {% if primary_issue.code == 'destination_mismatch' %}
              <a class="btn btn-warning" href="{{ url_for('driver.edit_driver_log', log_id=log.id) }}">Change destination</a>
```

### 330. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/view_driver_log.html:492`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
<form action="{{ url_for('driver.request_manager_review', log_id=log.id) }}" method="POST">
              <input type="hidden" name="reason" value="{{ primary_issue.label }}: {{ primary_issue.reason }}">
              <button class="btn btn-outline-danger" type="submit">Send to manager review</button>
            </form>
          </div>
          {% endif %}
        </div>
      </div>
    {% elif issue_closeout %}
      <div class="r
```

### 331. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/view_driver_log.html:492`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
" method="POST">
              <input type="hidden" name="reason" value="{{ primary_issue.label }}: {{ primary_issue.reason }}">
              <button class="btn btn-outline-danger" type="submit">Send to manager review</button>
            </form>
          </div>
          {% endif %}
        </div>
      </div>
    {% elif issue_closeout %}
      <div class="report-section">
        <div class="report-section-head green">Issue Closeou
```

### 332. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/view_driver_log.html:529`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
er.delete_driver_log_photo', photo_id=photo.id) }}" onsubmit="return confirm('Delete this stop photo proof?');">
                    <input type="hidden" name="next" value="{{ request.full_path }}">
                    <button class="proof-photo-delete" type="submit">Remove Photo</button>
                  </form>
                {% endif %}
              </div>
            {% endfor %}
          </div>
        </div>
      </div>
    {
```

### 333. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/view_driver_log.html:529`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
return confirm('Delete this stop photo proof?');">
                    <input type="hidden" name="next" value="{{ request.full_path }}">
                    <button class="proof-photo-delete" type="submit">Remove Photo</button>
                  </form>
                {% endif %}
              </div>
            {% endfor %}
          </div>
        </div>
      </div>
    {% endif %}
  {% endif %}

  {% set can_manage_log = current_us
```

### 334. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/view_driver_log.html:552`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
{% endif %}
      {% if can_delete_log %}
        <form action="{{ url_for('driver.delete_driver_log', log_id=log.id) }}" method="POST" class="d-inline" onsubmit="return confirm('Delete this driver log?');">
          <button type="submit" class="btn btn-outline-danger">Delete</button>
        </form>
      {% endif %}
    {% endif %}
  </div>
</div>
{% include 'partials/_md_bottom_nav.html' %}
{% endblock %}
```

### 335. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/view_driver_log.html:552`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
ion="{{ url_for('driver.delete_driver_log', log_id=log.id) }}" method="POST" class="d-inline" onsubmit="return confirm('Delete this driver log?');">
          <button type="submit" class="btn btn-outline-danger">Delete</button>
        </form>
      {% endif %}
    {% endif %}
  </div>
</div>
{% include 'partials/_md_bottom_nav.html' %}
{% endblock %}
```

### 336. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/view_driver_log.html:473`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'placeholder'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
dden" name="next" value="{{ url_for('driver.mobile_dashboard') }}">
              <label for="issueCloseoutReason">Closeout reason required</label>
              <textarea id="issueCloseoutReason" name="reason" required placeholder="Tell the manager why this can be closed and the route can continue."></textarea>
              <button class="btn btn-success" type="submit">{{ closeout_label }}</button>
            </form>
            {% i
```

### 337. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/manager_task_detail.html:81`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'click'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
p>{{ task.title }}{% if task.is_hot %} | Hot move{% endif %}</p>
    </div>
    <div class="header-actions">
      <a href="{{ url_for('manager.manager_dashboard') }}">Back to Dashboard</a>
      <button type="button" onclick="window.print()">Print Audit Log</button>
    </div>
  </header>

  <main class="detail-content">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        {% for category
```

### 338. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/manager_task_detail.html:13`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
margin:0; font-size:1.45rem; font-weight:900; }
  .detail-header p { margin:4px 0 0; color:#94a3b8; font-size:.86rem; }
  .header-actions { display:flex; gap:10px; flex-wrap:wrap; }
  .header-actions a, .header-actions button { border:1px solid rgba(148,163,184,.35); background:rgba(255,255,255,.08); color:#fff; border-radius:10px; padding:9px 12px; font-weight:900; text-decoration:none; font-size:.84rem; }
  .header-actions a:hover, .
```

### 339. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/manager_task_detail.html:14`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
:1px solid rgba(148,163,184,.35); background:rgba(255,255,255,.08); color:#fff; border-radius:10px; padding:9px 12px; font-weight:900; text-decoration:none; font-size:.84rem; }
  .header-actions a:hover, .header-actions button:hover { background:rgba(255,255,255,.14); }
  .detail-content { padding:26px; max-width:1180px; margin:0 auto; display:grid; gap:20px; }
  .summary-grid { display:grid; grid-template-columns:repeat(4, minmax(0, 1f
```

### 340. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/manager_task_detail.html:81`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
task.id }}</h1>
      <p>{{ task.title }}{% if task.is_hot %} | Hot move{% endif %}</p>
    </div>
    <div class="header-actions">
      <a href="{{ url_for('manager.manager_dashboard') }}">Back to Dashboard</a>
      <button type="button" onclick="window.print()">Print Audit Log</button>
    </div>
  </header>

  <main class="detail-content">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
```

### 341. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/manager_task_detail.html:81`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
1>
      <p>{{ task.title }}{% if task.is_hot %} | Hot move{% endif %}</p>
    </div>
    <div class="header-actions">
      <a href="{{ url_for('manager.manager_dashboard') }}">Back to Dashboard</a>
      <button type="button" onclick="window.print()">Print Audit Log</button>
    </div>
  </header>

  <main class="detail-content">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        {% fo
```

### 342. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/manager_task_detail.html:81`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
Hot move{% endif %}</p>
    </div>
    <div class="header-actions">
      <a href="{{ url_for('manager.manager_dashboard') }}">Back to Dashboard</a>
      <button type="button" onclick="window.print()">Print Audit Log</button>
    </div>
  </header>

  <main class="detail-content">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        {% for category, message in messages %}
          <div
```

### 343. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/manager_task_detail.html:162`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
detail">{{ task.details or '' }}</textarea>
            </div>
            <div class="save-row">
              <a class="btn-secondary-action" href="{{ url_for('manager.manager_dashboard') }}">Cancel</a>
              <button class="btn-primary-action" type="submit">Save Changes</button>
            </div>
          </form>
        </div>
      </div>

      <aside class="panel">
        <div class="panel-head"><h2>Audit Context</h2></
```

### 344. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/manager_task_detail.html:162`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
<div class="save-row">
              <a class="btn-secondary-action" href="{{ url_for('manager.manager_dashboard') }}">Cancel</a>
              <button class="btn-primary-action" type="submit">Save Changes</button>
            </div>
          </form>
        </div>
      </div>

      <aside class="panel">
        <div class="panel-head"><h2>Audit Context</h2></div>
        <div class="panel-body">
          <p class="labe
```

### 345. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/manager_task_detail.html:150`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'placeholder'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
</div>
              <div>
                <label for="part_number">Part Number</label>
                <input id="part_number" name="part_number" class="form-control" value="{{ task.part_number or '' }}" placeholder="Part number or hot parts ID">
              </div>
            </div>
            <div>
              <label class="checkline"><input type="checkbox" name="is_hot" value="y" {% if task.is_hot %}checked{% end
```

### 346. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/manager_task_detail.html:158`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'placeholder'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
Mark as HOT MOVE</label>
            </div>
            <div>
              <label for="details">Dispatch Notes / Skid / Trailer</label>
              <textarea id="details" name="details" rows="5" class="form-control" placeholder="Skid count, trailer number, dock notes, or compliance detail">{{ task.details or '' }}</textarea>
            </div>
            <div class="save-row">
              <a class="btn-secondary-action" href="{{
```

### 347. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/damage_evidence_packet.html:57`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'click'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
<div class="evidence-toolbar print-controls no-print">
    <a class="btn btn-outline-secondary" href="{{ back_url }}">Back to Report</a>
    <div class="actions">
      <button class="btn btn-primary" type="button" onclick="window.print()">Print Document</button>
    </div>
  </div>

  <section class="packet-page official-print-document">
    <header class="document-header print-only">
      <div>
        {% include 'partials/_md_pri
```

### 348. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/damage_evidence_packet.html:44`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
ock; } .packet-stamp { text-align:left; margin-top:10px; } }
  @media print {
    body { background:#fff !important; }
    .navbar, .evidence-toolbar, .no-print, .screen-only, .print-controls, .helper-text, .form-hint, .button-row, header.app-nav, #fullscreenOverlay { display:none !important; }
    .container.mt-4.fade-in { max-width:none; margin:0 !important; padding:0 !important; }
    .packet-page { border:0; border-radius:0; padding
```

### 349. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/damage_evidence_packet.html:57`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
at': packet.generated_at, 'page': '1 of 5'}) %}
  <div class="evidence-toolbar print-controls no-print">
    <a class="btn btn-outline-secondary" href="{{ back_url }}">Back to Report</a>
    <div class="actions">
      <button class="btn btn-primary" type="button" onclick="window.print()">Print Document</button>
    </div>
  </div>

  <section class="packet-page official-print-document">
    <header class="document-header print-only">
```

### 350. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/damage_evidence_packet.html:57`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
of 5'}) %}
  <div class="evidence-toolbar print-controls no-print">
    <a class="btn btn-outline-secondary" href="{{ back_url }}">Back to Report</a>
    <div class="actions">
      <button class="btn btn-primary" type="button" onclick="window.print()">Print Document</button>
    </div>
  </div>

  <section class="packet-page official-print-document">
    <header class="document-header print-only">
      <div>
        {% include 'partia
```

### 351. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/damage_evidence_packet.html:57`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
ontrols no-print">
    <a class="btn btn-outline-secondary" href="{{ back_url }}">Back to Report</a>
    <div class="actions">
      <button class="btn btn-primary" type="button" onclick="window.print()">Print Document</button>
    </div>
  </div>

  <section class="packet-page official-print-document">
    <header class="document-header print-only">
      <div>
        {% include 'partials/_md_print_signature.html' %}
        <h1>{{ do
```

### 352. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/plant_transfer_printable.html:66`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'click'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
.user_id == current_user.id %}
      <a class="edit-btn" href="{{ url_for('driver.edit_plant_transfer', transfer_id=transfer.id) }}">Edit Before Printing</a>
    {% endif %}
    <button class="print-btn" type="button" onclick="markPrintedAndPrint()">Print Document</button>
    <a class="email-btn" href="{{ url_for(transfer_print_endpoint, transfer_id=transfer.id, copy=requested_copy, autoprint=1) }}">Save PDF</a>
    <a class="back-btn"
```

### 353. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/plant_transfer_printable.html:15`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
; margin-bottom:0.06in; }
    .document-number { font-weight:900; }
    .screen-actions { display: flex; flex-wrap: wrap; gap: 0.08in; margin-bottom: 0.15in; align-items: center; }
    .screen-actions a, .screen-actions button { border: 0; padding: 8px 14px; color: #fff; text-decoration: none; cursor: pointer; font-size: 10pt; }
    .edit-btn { background: #8b1538; }
    .print-btn { background: #0069d9; }
    .back-btn { background: #3
```

### 354. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/plant_transfer_printable.html:48`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
pace-between; font-size:7.5pt; border-bottom:1px solid #000; padding-bottom:2px; margin-bottom:0.06in; }
    .document-number { font-weight:900; }
    .no-print, .screen-only, .print-controls, .helper-text, .form-hint, .button-row, nav, header.app-nav, .screen-actions { display: none !important; }
      .copy-page { width: 100%; min-height: auto; margin: 0; border: none; }
      * { -webkit-print-color-adjust: exact; print-color-adjust:
```

### 355. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/plant_transfer_printable.html:66`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
urrent_user.role == 'driver' and transfer.user_id == current_user.id %}
      <a class="edit-btn" href="{{ url_for('driver.edit_plant_transfer', transfer_id=transfer.id) }}">Edit Before Printing</a>
    {% endif %}
    <button class="print-btn" type="button" onclick="markPrintedAndPrint()">Print Document</button>
    <a class="email-btn" href="{{ url_for(transfer_print_endpoint, transfer_id=transfer.id, copy=requested_copy, autoprint=1)
```

### 356. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/plant_transfer_printable.html:66`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
d transfer.user_id == current_user.id %}
      <a class="edit-btn" href="{{ url_for('driver.edit_plant_transfer', transfer_id=transfer.id) }}">Edit Before Printing</a>
    {% endif %}
    <button class="print-btn" type="button" onclick="markPrintedAndPrint()">Print Document</button>
    <a class="email-btn" href="{{ url_for(transfer_print_endpoint, transfer_id=transfer.id, copy=requested_copy, autoprint=1) }}">Save PDF</a>
    <a class=
```

### 357. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/plant_transfer_printable.html:66`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
"edit-btn" href="{{ url_for('driver.edit_plant_transfer', transfer_id=transfer.id) }}">Edit Before Printing</a>
    {% endif %}
    <button class="print-btn" type="button" onclick="markPrintedAndPrint()">Print Document</button>
    <a class="email-btn" href="{{ url_for(transfer_print_endpoint, transfer_id=transfer.id, copy=requested_copy, autoprint=1) }}">Save PDF</a>
    <a class="back-btn" href="{{ url_for(transfer_view_endpoint, tran
```

### 358. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/plant_transfer_printable.html:143`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'dev'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
d: "POST",
        credentials: "same-origin"
      });
    } catch (err) {
      console.error('Could not record print activity:', err);
    }
    window.print();
  }
  {% if request.args.get('autoprint') %}
  window.addEventListener("load", function () {
    window.setTimeout(function () {
      markPrintedAndPrint();
    }, 150);
  });
  {% endif %}
</script>
</body>
</html>
```

### 359. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/plant_transfer_printable.html`
**Expected:** Audit printouts should use numbered sections or a clear ordered structure.
**Actual:** No obvious section numbering found in print-related file.
**Recommendation:** Number print sections and add a screenshot/PDF baseline.

### 360. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/manager_route_review.html:85`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'click'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
ent_meta = document_meta|default({'title': 'MANAGER ROUTE REVIEW', 'document_no': 'MGR-REVIEW-' ~ the_date, 'generated_at': '', 'page': '1 of 1'}) %}
  <div class="print-controls no-print">
  <button class="print-btn" onclick="window.print()">Print Document</button>
  <a class="email-btn" href="{{ attachment_url }}">Save PDF</a>
  {% if csv_url is defined %}<a class="email-btn" href="{{ csv_url }}">CSV Export</a>{% endif %}
  {% if shee
```

### 361. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/manager_route_review.html:78`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
ex; align-items:flex-end; }
    .sig-line img { max-height:0.38in; max-width:100%; }
    .muted { color:#555; }
    @media print { body { padding:0; } .no-print, .screen-only, .print-controls, .helper-text, .form-hint, .button-row, nav, header.app-nav, .print-btn, .email-btn, .print-guidance { display:none !important; } * { -webkit-print-color-adjust:exact; print-color-adjust:exact; } }
    {% include 'partials/_md_print_signature_style
```

### 362. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/manager_route_review.html:85`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
head>
<body>
  {% set document_meta = document_meta|default({'title': 'MANAGER ROUTE REVIEW', 'document_no': 'MGR-REVIEW-' ~ the_date, 'generated_at': '', 'page': '1 of 1'}) %}
  <div class="print-controls no-print">
  <button class="print-btn" onclick="window.print()">Print Document</button>
  <a class="email-btn" href="{{ attachment_url }}">Save PDF</a>
  {% if csv_url is defined %}<a class="email-btn" href="{{ csv_url }}">CSV Export<
```

### 363. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/manager_route_review.html:85`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
e': 'MANAGER ROUTE REVIEW', 'document_no': 'MGR-REVIEW-' ~ the_date, 'generated_at': '', 'page': '1 of 1'}) %}
  <div class="print-controls no-print">
  <button class="print-btn" onclick="window.print()">Print Document</button>
  <a class="email-btn" href="{{ attachment_url }}">Save PDF</a>
  {% if csv_url is defined %}<a class="email-btn" href="{{ csv_url }}">CSV Export</a>{% endif %}
  {% if sheets_url is defined %}<a class="email-btn
```

### 364. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/manager_route_review.html:373`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'dev'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
class="sig-line"></div>
          <small class="muted">Reviewed date/time: ____________________</small>
        </div>
      </div>
    </div>
  </div>
</main>
{% if request.args.get('autoprint') %}
<script>
  window.addEventListener("load", function () {
    window.setTimeout(function () {
      window.print();
    }, 150);
  });
</script>
{% endif %}
</body>
</html>
```

### 365. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/view_damage_report.html:79`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'click'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
rd') }}">Review</a>
      {% else %}
        <a class="btn btn-outline-secondary" href="{{ url_for('driver.damage_reports') }}">History</a>
      {% endif %}
      <button class="btn btn-outline-primary" type="button" onclick="window.print()">Print Document</button>
      {% if manager_view|default(false) %}
        <a class="btn btn-primary" href="{{ url_for('manager.damage_evidence_packet', report_id=report.id) }}">Proof Record</a>
```

### 366. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/view_damage_report.html:17`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
.locked { color:#334155; }
  .status-label.open { color:#166534; }
  .no-print, .screen-only { }
  .document-header { display:none; }
  @media print { .no-print, .screen-only, .print-controls, .helper-text, .form-hint, .button-row, nav, header.app-nav, .navbar, #fullscreenOverlay { display:none !important; } .document-header { display:flex; justify-content:space-between; border-bottom:2px solid #111; padding-bottom:8px; margin-bottom:12
```

### 367. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/view_damage_report.html:79`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
ine-secondary" href="{{ url_for('manager.review_dashboard') }}">Review</a>
      {% else %}
        <a class="btn btn-outline-secondary" href="{{ url_for('driver.damage_reports') }}">History</a>
      {% endif %}
      <button class="btn btn-outline-primary" type="button" onclick="window.print()">Print Document</button>
      {% if manager_view|default(false) %}
        <a class="btn btn-primary" href="{{ url_for('manager.damage_evidenc
```

### 368. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/view_damage_report.html:79`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
ew_dashboard') }}">Review</a>
      {% else %}
        <a class="btn btn-outline-secondary" href="{{ url_for('driver.damage_reports') }}">History</a>
      {% endif %}
      <button class="btn btn-outline-primary" type="button" onclick="window.print()">Print Document</button>
      {% if manager_view|default(false) %}
        <a class="btn btn-primary" href="{{ url_for('manager.damage_evidence_packet', report_id=report.id) }}">Proof Rec
```

### 369. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/view_damage_report.html:79`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
<a class="btn btn-outline-secondary" href="{{ url_for('driver.damage_reports') }}">History</a>
      {% endif %}
      <button class="btn btn-outline-primary" type="button" onclick="window.print()">Print Document</button>
      {% if manager_view|default(false) %}
        <a class="btn btn-primary" href="{{ url_for('manager.damage_evidence_packet', report_id=report.id) }}">Proof Record</a>
        <form method="POST" action="{{ ur
```

### 370. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/view_damage_report.html:84`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
) }}" onsubmit="return confirm('Archive this damage report from active review? Evidence will remain attached.');">
          <input type="hidden" name="next" value="{{ url_for('manager.review_dashboard') }}">
          <button class="btn btn-outline-danger" type="submit">Archive Report</button>
        </form>
      {% else %}
        <a class="btn btn-primary" href="{{ url_for('driver.damage_evidence_packet', report_id=report.id) }}">P
```

### 371. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/view_damage_report.html:84`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
ve review? Evidence will remain attached.');">
          <input type="hidden" name="next" value="{{ url_for('manager.review_dashboard') }}">
          <button class="btn btn-outline-danger" type="submit">Archive Report</button>
        </form>
      {% else %}
        <a class="btn btn-primary" href="{{ url_for('driver.damage_evidence_packet', report_id=report.id) }}">Proof Record</a>
      {% endif %}
      {% if can_modify|default(fal
```

### 372. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/view_damage_report.html:92`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
class="btn btn-primary" href="{{ url_for('driver.edit_damage_report', report_id=report.id) }}">Edit</a>
        <form method="POST" action="{{ url_for('driver.submit_damage_report', report_id=report.id) }}">
          <button class="btn btn-success" type="submit">Submit</button>
        </form>
        <details class="more-actions">
          <summary class="btn btn-outline-secondary">More Actions</summary>
          <form class="mt-2"
```

### 373. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/view_damage_report.html:92`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
t_damage_report', report_id=report.id) }}">Edit</a>
        <form method="POST" action="{{ url_for('driver.submit_damage_report', report_id=report.id) }}">
          <button class="btn btn-success" type="submit">Submit</button>
        </form>
        <details class="more-actions">
          <summary class="btn btn-outline-secondary">More Actions</summary>
          <form class="mt-2" method="POST" action="{{ url_for('driver.delete_dama
```

### 374. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/view_damage_report.html:97`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
<form class="mt-2" method="POST" action="{{ url_for('driver.delete_damage_report', report_id=report.id) }}" onsubmit="return confirm('Archive this damage report? Evidence will remain attached.');">
            <button class="btn btn-outline-danger btn-sm" type="submit">Archive Report</button>
          </form>
        </details>
      {% endif %}
    </div>
  </div>

  {% if not can_modify|default(false) and not manager_view|de
```

### 375. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/view_damage_report.html:97`
**Expected:** Print/PDF output should not include app controls, debug text, placeholders, or vague UI-only wording.
**Actual:** Print-related file contains 'button'.
**Recommendation:** Remove from print output or prove it is hidden by print CSS and add a print test.

```text
_damage_report', report_id=report.id) }}" onsubmit="return confirm('Archive this damage report? Evidence will remain attached.');">
            <button class="btn btn-outline-danger btn-sm" type="submit">Archive Report</button>
          </form>
        </details>
      {% endif %}
    </div>
  </div>

  {% if not can_modify|default(false) and not manager_view|default(false) %}
    <div class="alert alert-secondary small">This report is
```

### 376. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/partials/_md_bottom_nav.html`
**Expected:** Audit printouts should use numbered sections or a clear ordered structure.
**Actual:** No obvious section numbering found in print-related file.
**Recommendation:** Number print sections and add a screenshot/PDF baseline.

### 377. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/partials/_md_print_signature_styles.html`
**Expected:** Audit printouts should use numbered sections or a clear ordered structure.
**Actual:** No obvious section numbering found in print-related file.
**Recommendation:** Number print sections and add a screenshot/PDF baseline.

### 378. NEEDS REVIEW — printout wording/layout audit

**Location:** `templates/partials/_md_print_signature.html`
**Expected:** Audit printouts should use numbered sections or a clear ordered structure.
**Actual:** No obvious section numbering found in print-related file.
**Recommendation:** Number print sections and add a screenshot/PDF baseline.

### 379. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_all_pretrips.html:6`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: default table look.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
{% extends "base.html" %}
{% block title %}All PreTrips (Management){% endblock %}
{% block content %}
<h2>All PreTrips (Management View)</h2>
{% if pretrips %}
<table class="table table-hover align-middle">
  <thead class="table-dark">
    <tr>
      <th>ID</th>
      <th>User</th>
      <th>Date</th>
      <th>Truck</th>
      <th>Start Mileage</th>
      <th>PostTrip?</th>
```

### 380. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_dashboard.html:7`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
ay { display:none !important; }
  body.mgr-active .container.mt-4.fade-in { max-width:none; margin:0 !important; padding:0 !important; animation:none; opacity:1; }
  body.mgr-active { overflow-x:hidden; overflow-y:auto; background:#f8fafc; }

  *, *::before, *::after { box-sizing:border-box; }

  /* ── Layout shell ── */
  .mc { min-height:100vh; width:100%; display:flex; background:#f8fafc; color:#0f172a;
        font-family:-apple-sys
```

### 381. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_dashboard.html:12`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
ity:1; }
  body.mgr-active { overflow-x:hidden; overflow-y:auto; background:#f8fafc; }

  *, *::before, *::after { box-sizing:border-box; }

  /* ── Layout shell ── */
  .mc { min-height:100vh; width:100%; display:flex; background:#f8fafc; color:#0f172a;
        font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif; }

  /* ── Sidebar ── */
  .mc-side { width:256px; flex:0 0 256px; background:#0f172a; color:#cbd5e
```

### 382. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_dashboard.html:44`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
{ color:#475569; font-size:.68rem; margin:2px 0 0; }

  /* ── Main ── */
  .mc-main { flex:1 1 auto; min-width:0; display:flex; flex-direction:column; min-height:100vh; overflow:visible; }

  /* Header */
  .mc-header { background:#fff; border-bottom:1px solid #e2e8f0; padding:16px 28px;
               display:flex; align-items:center; justify-content:space-between; gap:14px;
               z-index:10; box-shadow:0 1px 2px rgba(15,23,42
```

### 383. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_dashboard.html:56`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
font-size:.85rem; width:250px; outline:none; color:#334155; font-family:inherit; }
  .mc-srch:focus { background:#e2e8f0; }
  .search-suggestions { position:absolute; top:calc(100% + 6px); left:0; right:0; background:#fff; border:1px solid #cbd5e1; border-radius:12px; box-shadow:0 14px 30px rgba(15,23,42,.16); z-index:80; overflow:hidden; display:none; }
  .search-suggestions.open { display:block; }
  .suggestion-item { wi
```

### 384. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_dashboard.html:58`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
der:1px solid #cbd5e1; border-radius:12px; box-shadow:0 14px 30px rgba(15,23,42,.16); z-index:80; overflow:hidden; display:none; }
  .search-suggestions.open { display:block; }
  .suggestion-item { width:100%; border:0; background:#fff; padding:9px 11px; display:flex; justify-content:space-between; gap:10px; cursor:pointer; text-align:left; font:inherit; }
  .suggestion-item:hover { background:#eff6ff; }
  .suggestion-term { color:#0f17
```

### 385. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_dashboard.html:79`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
isible; padding:22px 28px; display:flex; flex-direction:column; gap:18px; min-width:0; }

  /* ── KPI cards ── */
  .kpi-row { display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:10px; }
  .kpi { background:#fff; border:1px solid #e2e8f0; border-radius:10px;
         padding:12px 14px; box-shadow:0 1px 2px rgba(15,23,42,.04); text-decoration:none; display:block; cursor:pointer; transition:transform .15s, box-shad
```

### 386. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_dashboard.html:85`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
09); border-color:#93c5fd; }
  .kpi.active { outline:2px solid rgba(37,99,235,.35); }
  .kpi.blue  { background:#eff6ff; border-color:#bfdbfe; }
  .kpi.green { background:#ecfdf5; border-color:#a7f3d0; }
  .kpi.danger { background:#fff1f2; border-color:#fecdd3; }
  .kpi-lbl { font-size:.64rem; font-weight:900; text-transform:uppercase;
             letter-spacing:.07em; color:#64748b; margin:0 0 5px; }
  .kpi.blue  .kpi-lbl { color:#256
```

### 387. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_dashboard.html:100`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
; }
  .kpi.blue  .kpi-tag { background:#bfdbfe; color:#1d4ed8; }
  .kpi.green .kpi-tag { background:#a7f3d0; color:#047857; }
  .kpi.danger .kpi-tag { background:#ffe4e6; color:#be123c; }

  /* ── Panel ── */
  .panel { background:#fff; border:1px solid #e2e8f0; border-radius:18px;
           scroll-margin-top:22px;
           box-shadow:0 1px 2px rgba(15,23,42,.04); overflow:visible; }
  .panel.focus-panel,
  .capture-panel.focus-panel
```

### 388. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_dashboard.html:119`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
0 18px 42px rgba(15,23,42,.12); }
    58% { box-shadow:0 0 0 11px rgba(245,158,11,0), 0 18px 42px rgba(15,23,42,.12); }
    100% { transform:none; }
  }
  .panel-top { padding:14px 20px; border-bottom:1px solid #e2e8f0; background:#f8fafc;
               display:flex; align-items:center; justify-content:space-between;
               gap:12px; flex-wrap:wrap; }
  .panel-top h3 { font-size:.95rem; font-weight:900; color:#0f172a; margin:0;
```

### 389. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_dashboard.html:131`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
div-tabs a { text-decoration:none; color:#64748b; font-weight:800; font-size:.8rem;
                padding:6px 14px; border-radius:8px; transition:all .15s; white-space:normal; line-height:1.2; }
  .div-tabs a.active { background:#fff; color:#1d4ed8; box-shadow:0 1px 3px rgba(15,23,42,.1); }
  .div-tabs a:hover:not(.active) { color:#334155; }

  /* ── Table ── */
  .tbl-wrap { max-width:100%; overflow-x:auto; -webkit-overflow-scrolling
```

### 390. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_dashboard.html:141`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
table.dtbl th { padding:11px 14px; text-align:left; font-size:.63rem; font-weight:900;
                  text-transform:uppercase; letter-spacing:.07em; color:#64748b;
                  border-bottom:1px solid #e2e8f0; background:#f8fafc; white-space:nowrap; }
  table.dtbl th:last-child { text-align:right; }
  table.dtbl td { padding:13px 14px; border-bottom:1px solid #f1f5f9; vertical-align:middle; overflow-wrap:anywhere; }
  .align-m
```

### 391. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_dashboard.html:174`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
, .truck-meta { font-size:.72rem; color:#64748b; font-weight:700; line-height:1.25; }
  .truck-pill { display:inline-flex; align-items:center; gap:5px; margin-top:4px; padding:3px 8px;
                border-radius:8px; background:#f8fafc; border:1px solid #e2e8f0;
                color:#334155; font-size:.72rem; font-weight:900; white-space:nowrap; }
  .truck-pill.missing { color:#b45309; background:#fffbeb; border-color:#fde68a; }
  .
```

### 392. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_dashboard.html:176`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
ng:3px 8px;
                border-radius:8px; background:#f8fafc; border:1px solid #e2e8f0;
                color:#334155; font-size:.72rem; font-weight:900; white-space:nowrap; }
  .truck-pill.missing { color:#b45309; background:#fffbeb; border-color:#fde68a; }
  .d-av { width:26px; height:26px; border-radius:999px; background:#e2e8f0; color:#475569;
          display:grid; place-items:center; font-size:.64rem; font-weight:900; flex-s
```

### 393. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_dashboard.html:180`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
:grid; place-items:center; font-size:.64rem; font-weight:900; flex-shrink:0; }
  .unassigned-cell { display:inline-flex; align-items:center; gap:5px; font-size:.8rem;
                     font-weight:900; color:#be123c; background:#fff1f2;
                     padding:4px 9px; border-radius:8px; }
  .unassigned-cell svg { width:13px; height:13px; }

  /* Status badge */
  .sbadge { display:inline-flex; align-items:center; padding:4px 9p
```

### 394. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_dashboard.html:202`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
x; max-width:100%; color:#991b1b; font-size:.72rem; line-height:1.25; font-weight:800; overflow-wrap:anywhere; }
  .problem-thumb { width:42px; height:32px; object-fit:cover; border-radius:6px; border:1px solid #fecaca; background:#fff; flex:0 0 42px; }
  .problem-label { color:#be123c; text-transform:uppercase; letter-spacing:.04em; font-size:.62rem; display:block; }
  .critical-list { display:grid; gap:8px; padding:12px 16px; max-heig
```

### 395. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_dashboard.html:205`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
overflow-y:auto; overscroll-behavior:contain; }
  .critical-row { display:grid; grid-template-columns:minmax(120px,.8fr) minmax(150px,1fr) minmax(0,2fr) auto; gap:10px; align-items:flex-start; border:1px solid #fee2e2; background:#fff7f7; border-radius:10px; padding:10px; color:#991b1b; text-decoration:none; min-height:max-content; }
  .critical-row:hover { background:#fff1f2; color:#991b1b; }
  .critical-type { font-size:.68rem; font-
```

### 396. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_dashboard.html:206`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
inmax(0,2fr) auto; gap:10px; align-items:flex-start; border:1px solid #fee2e2; background:#fff7f7; border-radius:10px; padding:10px; color:#991b1b; text-decoration:none; min-height:max-content; }
  .critical-row:hover { background:#fff1f2; color:#991b1b; }
  .critical-type { font-size:.68rem; font-weight:900; text-transform:uppercase; letter-spacing:.06em; color:#be123c; }
  .critical-stop { font-size:.82rem; font-weight:900; color:#0f1
```

### 397. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_dashboard.html:211`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
ception-chip-list { display:flex; flex-wrap:wrap; gap:5px; max-width:100%; }
  .exception-chip { display:inline-flex; align-items:center; gap:4px; padding:3px 7px; border-radius:999px; font-size:.64rem; font-weight:900; background:#fff7ed; color:#9a3412; border:1px solid #fed7aa; white-space:normal; line-height:1.2; }
  .exception-chip.damage { background:#fff1f2; color:#be123c; border-color:#fecdd3; }
  .exception-chip.missing { backgr
```

### 398. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_dashboard.html:212`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
ms:center; gap:4px; padding:3px 7px; border-radius:999px; font-size:.64rem; font-weight:900; background:#fff7ed; color:#9a3412; border:1px solid #fed7aa; white-space:normal; line-height:1.2; }
  .exception-chip.damage { background:#fff1f2; color:#be123c; border-color:#fecdd3; }
  .exception-chip.missing { background:#fef3c7; color:#92400e; border-color:#fde68a; }
  .exception-chip.truck { background:#eff6ff; color:#1d4ed8; border-color:
```

### 399. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_dashboard.html:219`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
llow { 70% { box-shadow:0 0 0 8px rgba(245,158,11,0); } 100% { box-shadow:0 0 0 0 rgba(245,158,11,0); } }
  .driver-filter-row { display:flex; flex-wrap:wrap; gap:7px; padding:12px 20px; border-bottom:1px solid #e2e8f0; background:#fff; }
  .driver-filter-row a { text-decoration:none; border:1px solid #cbd5e1; border-radius:999px; padding:5px 11px; color:#334155; font-size:.78rem; font-weight:900; background:#fff; }
  .driver-filter-row
```

### 400. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_dashboard.html:220`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
20px; border-bottom:1px solid #e2e8f0; background:#fff; }
  .driver-filter-row a { text-decoration:none; border:1px solid #cbd5e1; border-radius:999px; padding:5px 11px; color:#334155; font-size:.78rem; font-weight:900; background:#fff; }
  .driver-filter-row a.active { background:#0f172a; color:#fff; border-color:#0f172a; }
  .live-route-stack { display:grid; gap:3px; }
  .live-route-main { font-weight:900; color:#0f172a; overflow-wrap
```

### 401. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_dashboard.html:233`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
}
  .plant-timing-strip { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:8px; padding:10px 20px 14px; }
  .plant-timing-card { border:1px solid #e2e8f0; border-radius:10px; padding:9px 10px; background:#f8fafc; min-width:0; overflow-wrap:anywhere; }
  .plant-timing-card strong { display:block; font-size:.86rem; line-height:1.25; }
  .plant-timing-card span { display:block; color:#64748b; font-size:.72rem; ma
```

### 402. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_dashboard.html:268`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
ite-space:normal; line-height:1.2; }
  .capture-card-actions button:hover { border-color:#60a5fa; }
  .capture-empty { color:#94a3b8; margin:0; font-size:.84rem; font-weight:700; }

  /* Manage button */
  .btn-manage { background:#fff; border:1px solid #cbd5e1; color:#334155;
                border-radius:10px; padding:6px 13px; font-size:.8rem; font-weight:800;
                cursor:pointer; transition:all .15s; white-space:normal; l
```

### 403. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_dashboard.html:271`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
der-radius:10px; padding:6px 13px; font-size:.8rem; font-weight:800;
                cursor:pointer; transition:all .15s; white-space:normal; line-height:1.2; }
  .btn-manage:hover { border-color:#93c5fd; color:#1d4ed8; background:#f8fafc; }
  .btn-manage:active { transform:scale(.97); }

  /* Empty row */
  .empty-row td { text-align:center; padding:40px 14px; color:#94a3b8;
                  font-size:.9rem; font-weight:600; }

  /* ─
```

### 404. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_dashboard.html:283`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
inset:0; background:rgba(15,23,42,.55);
            backdrop-filter:blur(4px); z-index:300; display:none;
            align-items:center; justify-content:center; padding:14px; }
  .mbdrop.open { display:flex; }
  .mdl { background:#fff; border-radius:20px; width:100%; max-width:500px;
         box-shadow:0 24px 60px rgba(15,23,42,.22); border:1px solid #e2e8f0;
         display:flex; flex-direction:column; overflow:hidden; max-height:92
```

### 405. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_dashboard.html:298`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
ace-items:center; }
  .mdl-x:hover { color:#fff; }
  .mdl-x svg { width:20px; height:20px; }
  .mdl-body { padding:22px; overflow-y:auto; display:flex; flex-direction:column; gap:16px; }
  .mdl-foot { padding:14px 22px; background:#f8fafc; border-top:1px solid #e2e8f0;
              display:flex; justify-content:flex-end; gap:10px; flex-shrink:0; }

  /* Modal context row */
  .mrow-ctx { display:flex; justify-content:space-between; ali
```

### 406. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_dashboard.html:313`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
{ display:block; font-size:.78rem; font-weight:800; color:#334155; margin-bottom:6px; }
  .flbl svg { width:13px; height:13px; vertical-align:-.1em; margin-right:4px; color:#94a3b8; }
  .fi, .fs, .fta {
    width:100%; background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px;
    padding:9px 13px; font-size:.875rem; color:#334155; outline:none; font-family:inherit;
    transition:border-color .15s,box-shadow .15s;
  }
  .fi:foc
```

### 407. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_dashboard.html:318`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
adius:10px;
    padding:9px 13px; font-size:.875rem; color:#334155; outline:none; font-family:inherit;
    transition:border-color .15s,box-shadow .15s;
  }
  .fi:focus, .fs:focus, .fta:focus {
    border-color:#93c5fd; background:#fff;
    box-shadow:0 0 0 3px rgba(147,197,253,.2);
  }
  .fta { resize:vertical; min-height:62px; }
  .act-grid { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
  .btn-amber { background:#fffbeb; b
```

### 408. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_dashboard.html:323`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
order-color:#93c5fd; background:#fff;
    box-shadow:0 0 0 3px rgba(147,197,253,.2);
  }
  .fta { resize:vertical; min-height:62px; }
  .act-grid { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
  .btn-amber { background:#fffbeb; border:1px solid #fde68a; color:#b45309; border-radius:12px;
               padding:11px 14px; font-size:.8rem; font-weight:900; cursor:pointer;
               display:flex; align-items:center; justif
```

### 409. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_dashboard.html:138`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: default table look.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
.tbl-wrap.live-stops-scroll { max-height:min(78vh,960px); overflow:auto; overscroll-behavior:contain; }
  .tbl-wrap.live-stops-scroll table.dtbl thead th { position:sticky; top:0; z-index:2; }
  table.dtbl { width:100%; border-collapse:collapse; min-width:720px; }
  table.dtbl th { padding:11px 14px; text-align:left; font-size:.63rem; font-weight:900;
                  text-transform:uppercase; letter-spacing:.07em; color:#64748b;
```

### 410. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_dashboard.html:877`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: default table look.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
Stops Awaiting Manager Review
          </h3>
          <a class="text-sm text-muted" href="{{ url_for('manager.review_queue') }}">Open full queue &rarr;</a>
        </div>
        <div class="tbl-wrap">
          <table class="dtbl">
            <thead>
              <tr>
                <th>Stop</th>
                <th>Reason</th>
                <th>Cargo (In &rarr; Out)</th>
                <th>Requested By</th>
```

### 411. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_dashboard.html:961`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: default table look.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
an>
              {% endif %}
            </div>
          {% endfor %}
        </div>
        {% endif %}
        <div class="tbl-wrap live-stops-scroll" tabindex="0" aria-label="Scrollable live route stops">
          <table class="dtbl" id="liveStopsTable">
            <thead>
              <tr>
                <th>Stop</th>
                <th>Driver</th>
                <th>Route / Plant</th>
                <th>Cargo</th>
```

### 412. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_dashboard.html:1051`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: default table look.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
% endif %}"
                 href="{{ url_for('manager.manager_dashboard', division=tab, focus='jobs') }}">{{ tab }}</a>
            {% endfor %}
          </div>
        </div>

        <div class="tbl-wrap">
          <table class="dtbl" id="dispatchTable">
            <thead>
              <tr>
                <th>Move ID</th>
                <th>Division</th>
                <th>Part / Skid</th>
                <th>Route</th>
```

### 413. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_drivers.html:6`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: default table look.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
{% extends "base.html" %}
{% block title %}All Drivers{% endblock %}
{% block content %}
<h2>All Drivers</h2>
{% if users %}
<table class="table table-striped">
  <thead class="table-dark">
    <tr>
      <th>ID</th>
      <th>Username</th>
      <th>Email</th>
      <th>Role</th>
    </tr>
  </thead>
  <tbody>
    {% for u in users %}
    <tr
```

### 414. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_task_detail.html:4`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
{% extends "base.html" %}
{% block content %}
<style>
  body { background:#f8fafc; }
  body.manager-shell-active .navbar,
  body.manager-shell-active #fullscreenOverlay { display:none !important; }
  body.manager-shell-active .container.mt-4.fade-in { max-width:none; margin:0 !impor
```

### 415. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_task_detail.html:8`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
creenOverlay { display:none !important; }
  body.manager-shell-active .container.mt-4.fade-in { max-width:none; margin:0 !important; padding:0 !important; animation:none; opacity:1; }
  .detail-shell { min-height:100vh; background:#f8fafc; color:#1e293b; font-family:Montserrat, Arial, sans-serif; }
  .detail-header { background:#0f172a; color:#fff; padding:22px 28px; display:flex; align-items:center; justify-content:space-between; gap:1
```

### 416. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_task_detail.html:17`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
.14); }
  .detail-content { padding:26px; max-width:1180px; margin:0 auto; display:grid; gap:20px; }
  .summary-grid { display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); gap:14px; }
  .summary-card, .panel { background:#fff; border:1px solid #e2e8f0; border-radius:16px; box-shadow:0 1px 2px rgba(15,23,42,.04); }
  .summary-card { padding:18px; }
  .label { margin:0 0 6px; color:#64748b; font-size:.72rem; font-weight:900; tex
```

### 417. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_task_detail.html:27`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
123c; border-color:#fecdd3; }
  .detail-grid { display:grid; grid-template-columns:minmax(0, 1.2fr) minmax(320px, .8fr); gap:20px; align-items:start; }
  .panel-head { padding:18px 20px; border-bottom:1px solid #e2e8f0; background:#f8fafc; }
  .panel-head h2 { margin:0; font-size:1.05rem; font-weight:900; }
  .panel-body { padding:20px; }
  .manager-form { display:grid; gap:16px; }
  .form-row { display:grid; grid-template-columns:1fr 1
```

### 418. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_task_detail.html:37`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
p:10px; flex-wrap:wrap; padding-top:4px; }
  .btn-primary-action { border:0; background:#2563eb; color:white; border-radius:10px; padding:10px 16px; font-weight:900; }
  .btn-secondary-action { border:1px solid #cbd5e1; background:#fff; color:#334155; border-radius:10px; padding:10px 16px; font-weight:900; text-decoration:none; }
  .log-list { display:grid; gap:10px; }
  .log-item { border:1px solid #e2e8f0; border-radius:12px; padding:
```

### 419. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_task_detail.html:39`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
ound:#fff; color:#334155; border-radius:10px; padding:10px 16px; font-weight:900; text-decoration:none; }
  .log-list { display:grid; gap:10px; }
  .log-item { border:1px solid #e2e8f0; border-radius:12px; padding:12px; background:#fff; }
  .log-item strong { color:#0f172a; }
  @media (max-width:900px) {
    .detail-header { align-items:flex-start; flex-direction:column; }
    .summary-grid, .detail-grid, .form-row { grid-template-colum
```

### 420. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_task_detail.html:49`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
.detail-grid, .form-row { grid-template-columns:1fr; }
    .detail-content { padding:16px; }
  }
  .print-management-title { display:none; }
  @media print {
    @page { size: Letter portrait; margin:.35in; }
    body { background:#fff !important; font-size:9pt; }
    .header-actions, .manager-form, .save-row, .navbar, #fullscreenOverlay { display:none !important; }
    body.manager-shell-active .container.mt-4.fade-in { padding:0 !impo
```

### 421. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_task_detail.html:52`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
.header-actions, .manager-form, .save-row, .navbar, #fullscreenOverlay { display:none !important; }
    body.manager-shell-active .container.mt-4.fade-in { padding:0 !important; }
    .detail-shell { min-height:auto; background:#fff; }
    .detail-header { background:#fff !important; color:#000; border-bottom:2px solid #111; padding:0 0 .08in; margin-bottom:.12in; }
    .detail-header h1 { font-size:15pt; }
    .detail-header p { col
```

### 422. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_task_detail.html:53`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
-row, .navbar, #fullscreenOverlay { display:none !important; }
    body.manager-shell-active .container.mt-4.fade-in { padding:0 !important; }
    .detail-shell { min-height:auto; background:#fff; }
    .detail-header { background:#fff !important; color:#000; border-bottom:2px solid #111; padding:0 0 .08in; margin-bottom:.12in; }
    .detail-header h1 { font-size:15pt; }
    .detail-header p { color:#333; font-size:8.5pt; }
    .print-m
```

### 423. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_task_detail.html:62`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
d, .panel { box-shadow:none; border:1px solid #222; border-radius:0; break-inside:avoid; }
    .summary-card { padding:.08in; }
    .detail-grid { grid-template-columns:1fr; gap:.12in; }
    .panel-head { padding:.08in; background:#fff; border-bottom:1px solid #222; }
    .panel-head h2 { font-size:10pt; }
    .panel-body { padding:.08in; }
    .log-list { gap:.05in; }
    .log-item { border:1px solid #999; border-radius:0; padding:.06i
```

### 424. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_review.html:6`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
nOverlay { display:none !important; }
  body.mgr-active .container.mt-4.fade-in { max-width:none; margin:0 !important; padding:0 !important; animation:none; opacity:1; }
  .review-shell { min-height:100vh; display:flex; background:#f8fafc; color:#0f172a; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif; }
  .review-side { width:256px; flex:0 0 256px; min-height:100vh; background:#0f172a; color:#cbd5e1; displa
```

### 425. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_review.html:15`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
border-radius:12px; font-weight:800; font-size:.85rem; }
  .review-nav a.active { background:rgba(37,99,235,.18); color:#60a5fa; }
  .review-main { flex:1; min-width:0; height:100vh; overflow:auto; }
  .review-header { background:#fff; border-bottom:1px solid #e2e8f0; padding:18px 28px; display:flex; align-items:center; justify-content:space-between; gap:14px; flex-wrap:wrap; }
  .review-header h2 { margin:0; font-size:1.5rem; font-wei
```

### 426. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_review.html:20`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
0; color:#64748b; font-size:.84rem; font-weight:700; }
  .review-body { padding:22px 28px; display:grid; gap:18px; }
  .metric-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; }
  .metric { background:#fff; border:1px solid #e2e8f0; border-radius:10px; padding:12px 14px; }
  .metric span { display:block; color:#64748b; font-size:.64rem; font-weight:900; text-transform:uppercase; letter-spacing:.07em; }
  .m
```

### 427. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_review.html:23`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
ont-size:.64rem; font-weight:900; text-transform:uppercase; letter-spacing:.07em; }
  .metric strong { display:block; margin-top:5px; color:#0f172a; font-size:1.65rem; line-height:1; font-weight:900; }
  .review-panel { background:#fff; border:1px solid #e2e8f0; border-radius:14px; overflow:hidden; }
  .review-panel-head { padding:13px 16px; border-bottom:1px solid #e2e8f0; background:#f8fafc; display:flex; justify-content:space-between
```

### 428. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_review.html:24`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
e:1.65rem; line-height:1; font-weight:900; }
  .review-panel { background:#fff; border:1px solid #e2e8f0; border-radius:14px; overflow:hidden; }
  .review-panel-head { padding:13px 16px; border-bottom:1px solid #e2e8f0; background:#f8fafc; display:flex; justify-content:space-between; gap:10px; align-items:center; }
  .review-panel-head h3 { margin:0; color:#0f172a; font-size:.95rem; font-weight:900; }
  .review-panel-head span { color:#
```

### 429. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_review.html:28`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
font-weight:900; }
  .review-panel-head span { color:#64748b; font-size:.72rem; font-weight:800; }
  .exception-table { width:100%; border-collapse:collapse; min-width:820px; }
  .exception-table th { padding:10px 12px; background:#f8fafc; border-bottom:1px solid #e2e8f0; color:#64748b; font-size:.64rem; font-weight:900; text-transform:uppercase; letter-spacing:.07em; text-align:left; }
  .exception-table td { padding:11px 12px; border-
```

### 430. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_review.html:42`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
ntent:flex-end; gap:6px; flex-wrap:wrap; }
  .review-actions form { margin:0; }
  .more-actions summary { cursor:pointer; list-style:none; }
  .more-actions summary::-webkit-details-marker { display:none; }
  .foldout { background:#fff; border:1px solid #e2e8f0; border-radius:12px; padding:0; overflow:hidden; }
  .foldout summary { padding:12px 14px; cursor:pointer; font-weight:900; color:#0f172a; background:#f8fafc; }
  .foldout-body {
```

### 431. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_review.html:43`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
-marker { display:none; }
  .foldout { background:#fff; border:1px solid #e2e8f0; border-radius:12px; padding:0; overflow:hidden; }
  .foldout summary { padding:12px 14px; cursor:pointer; font-weight:900; color:#0f172a; background:#f8fafc; }
  .foldout-body { padding:14px; }
  .damage-mini-list { display:grid; gap:8px; }
  .damage-mini-row { display:flex; align-items:stretch; gap:8px; }
  .damage-mini-row a { flex:1; min-width:0; text-d
```

### 432. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_review.html:51`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
ni-row button { white-space:nowrap; }
  .timing-list { display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:9px; }
  .timing-card { border:1px solid #e2e8f0; border-radius:10px; padding:10px 12px; background:#fff; }
  .timing-card strong { display:block; color:#0f172a; font-size:.92rem; }
  .timing-card span { display:block; color:#64748b; font-size:.75rem; font-weight:700; margin-top:3px; }
  @media (max-width:96
```

### 433. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_review.html:27`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: default table look.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
gn-items:center; }
  .review-panel-head h3 { margin:0; color:#0f172a; font-size:.95rem; font-weight:900; }
  .review-panel-head span { color:#64748b; font-size:.72rem; font-weight:800; }
  .exception-table { width:100%; border-collapse:collapse; min-width:820px; }
  .exception-table th { padding:10px 12px; background:#f8fafc; border-bottom:1px solid #e2e8f0; color:#64748b; font-size:.64rem; font-weight:900; text-transform:uppercase; let
```

### 434. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_review.html:114`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: default table look.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
ses %}
      <section class="review-panel">
        <div class="review-panel-head"><h3>Grouped Management Cases</h3><span>Related history, not route evidence</span></div>
        <div class="table-responsive">
          <table class="exception-table">
            <thead><tr><th>Case</th><th>Summary</th><th>Signals</th><th>Owner</th><th>Status</th></tr></thead>
            <tbody>
              {% for case in followup_cases %}
```

### 435. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_review.html:129`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: default table look.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
% endif %}

      <section class="review-panel">
        <div class="review-panel-head"><h3>Exception Inbox</h3><span>View, resolve, or escalate from the row</span></div>
        <div class="table-responsive">
          <table class="exception-table">
            <thead><tr><th>Priority</th><th>Type</th><th>Route / Stop</th><th>Issue</th><th>Owner</th><th>Age</th><th></th></tr></thead>
            <tbody>
              {% for item in ex
```

### 436. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_route_review.html:9`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
>Manager Route Review</title>
  <style>
    @page { size: Letter portrait; margin: 0.35in; }
    * { box-sizing: border-box; }
    body { margin:0; padding:1rem; font-family:Arial, sans-serif; font-size:9pt; color:#111; background:#fff; }
    .no-print, .screen-only { }
    .print-controls { margin-bottom:0.12in; }
    .official-print-document { width:100%; }
    .document-header { display:flex; justify-content:space-between; gap:0.2in;
```

### 437. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_route_review.html:32`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
111; margin-top:0.1in; break-inside:avoid; }
    .section h2 { background:#f1f5f9; padding:0.06in 0.08in; border-bottom:1px solid #111; }
    .section-body { padding:0.08in; }
    .action-section { border-color:#b45309; background:#fffbeb; }
    .action-section h2 { background:#fef3c7; color:#92400e; border-bottom-color:#b45309; }
    .action-section .section-body { background:#fffbeb; }
    .blocked-section { border-color:#b91c1c; back
```

### 438. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_route_review.html:34`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
n-body { padding:0.08in; }
    .action-section { border-color:#b45309; background:#fffbeb; }
    .action-section h2 { background:#fef3c7; color:#92400e; border-bottom-color:#b45309; }
    .action-section .section-body { background:#fffbeb; }
    .blocked-section { border-color:#b91c1c; background:#fef2f2; }
    .blocked-section h2 { background:#fee2e2; color:#991b1b; border-bottom-color:#b91c1c; }
    .blocked-list { margin:0; padding-l
```

### 439. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_route_review.html:47`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
color:#334155; line-height:1.25; }
    .audit-grid { display:grid; grid-template-columns:repeat(4, 1fr); gap:0.07in; margin-bottom:0.08in; }
    .audit-item { border:1px solid #cbd5e1; padding:0.06in; min-height:0.5in; background:#fff; }
    .audit-item strong { display:block; font-size:7pt; text-transform:uppercase; letter-spacing:.05em; color:#475569; }
    .audit-item span { display:block; font-size:9.2pt; font-weight:900; margin-to
```

### 440. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_route_review.html:53`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
; margin-top:2px; color:#334155; line-height:1.25; }
    .audit-item.clean { border-color:#86efac; background:#f0fdf4; }
    .audit-item.clean span { color:#166534; }
    .audit-item.needs-review { border-color:#f59e0b; background:#fffbeb; }
    .audit-item.needs-review span { color:#92400e; }
    .audit-item.warning { border-color:#facc15; background:#fefce8; }
    .audit-item.warning span { color:#854d0e; }
    .audit-item.ok span { c
```

### 441. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_route_review.html:68`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
ap:0.08in; }
    .photo-card { border:1px solid #111; padding:0.06in; min-height:2.55in; }
    .photo-card img { width:100%; height:2.15in; object-fit:contain; border:1px solid #94a3b8; display:block; margin-bottom:4px; background:#f8fafc; }
    .photo-missing { min-height:2.15in; display:grid; place-items:center; background:#fff7ed; border:1px solid #b45309; color:#92400e; font-weight:900; margin-bottom:4px; padding:6px; text-align:cen
```

### 442. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_route_review.html:69`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
photo-card img { width:100%; height:2.15in; object-fit:contain; border:1px solid #94a3b8; display:block; margin-bottom:4px; background:#f8fafc; }
    .photo-missing { min-height:2.15in; display:grid; place-items:center; background:#fff7ed; border:1px solid #b45309; color:#92400e; font-weight:900; margin-bottom:4px; padding:6px; text-align:center; line-height:1.25; }
    .photo-missing.hidden { display:none; }
    .check-grid { display:g
```

### 443. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_route_review.html:63`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: default table look.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
34; }
    .delay-status.warning { background:#fef3c7; color:#92400e; }
    .delay-status.high { background:#fee2e2; color:#991b1b; }
    .delay-status.muted { background:#f1f5f9; color:#475569; }
    table { width:100%; border-collapse:collapse; table-layout:fixed; }
    th, td { border:1px solid #111; padding:5px 6px; vertical-align:top; overflow-wrap:anywhere; }
    th { background:#f1f5f9; text-transform:uppercase; font-size:7pt; let
```

### 444. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_route_review.html:174`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: default table look.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
iew.status == 'Pending' else 'clean') }}"><strong>Total Route Mileage</strong><span>{{ mileage_review.label }}</span><small>{{ mileage_review.detail }}</small></div>
      </div>
      {% if mileage_review.rows %}
      <table>
        <thead><tr><th>Scope</th><th>Truck / PreTrip</th><th>Start Odometer</th><th>End Odometer</th><th>Calculated Route Miles</th><th>Status</th></tr></thead>
        <tbody>
          {% for row in mileage_rev
```

### 445. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_route_review.html:191`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: default table look.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
2>
    <div class="section-body">
      <p><strong>Related history only. These cases do not become route evidence unless a record is tied to this route, stop, driver log, driver, truck, or shift/date.</strong></p>
      <table>
        <thead><tr><th>Case</th><th>Summary</th><th>Signals</th><th>Owner</th><th>Status</th></tr></thead>
        <tbody>
          {% for case in followup_cases %}
            <tr><td>{{ case.title }}</td><td>{
```

### 446. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_route_review.html:235`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: default table look.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
m.value }}</span><small>{{ item.detail }}</small></div>
        {% endfor %}
      </div>
      {% if cargo_review.pending_scan_rows %}
        <h3 class="h6 text-uppercase text-muted">Pending Scan Evidence</h3>
        <table>
          <thead><tr><th>Scan</th><th>Stop</th><th>Context</th><th>Status</th><th>Value</th><th>Time</th></tr></thead>
          <tbody>
            {% for row in cargo_review.pending_scan_rows %}
              <
```

### 447. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_route_review.html:246`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: default table look.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
.time }}</td></tr>
            {% endfor %}
          </tbody>
        </table>
      {% endif %}
      {% if cargo_review.timing_rows %}
        <h3 class="h6 text-uppercase text-muted">Timing Intelligence</h3>
        <table>
          <thead><tr><th>Stop</th><th>Load / Dock Time</th><th>Plant Average</th><th>Status</th></tr></thead>
          <tbody>
            {% for row in cargo_review.timing_rows %}
              <tr><td>{{ row.p
```

### 448. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_route_review.html:265`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: default table look.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
as filed. Cargo/photo proof requires manager classification.</strong></p>{% endif %}
      {% if damage_reports %}<p><strong>{{ damage_report_summary }}.</strong></p>{% endif %}
      {% if damage_report_rows %}
        <table>
          <thead><tr><th>Incident</th><th>Type</th><th>Stop</th><th>Status</th><th>Photo Attached</th><th>Driver Note</th><th>Manager Classification</th></tr></thead>
          <tbody>
            {% for row in d
```

### 449. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_route_review.html:309`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: default table look.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
>
        {% endfor %}
      </div>
      {% endif %}
    </div>
  </div>
  {% endif %}

  {% if delay_review_rows %}
  <div class="section">
    <h2>9. Delay / Dock Time Review</h2>
    <div class="section-body">
      <table><thead><tr><th>Stop</th><th>Dock Time</th><th>Load-Time Status</th><th>Reason</th></tr></thead><tbody>
      {% for row in delay_review_rows %}<tr><td>{{ row.plant }}</td><td>{{ row.dock_wait }}</td><td><span clas
```

### 450. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_route_review.html:320`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: default table look.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
ion }}</strong>{% endif %}</td></tr>{% endfor %}
      </tbody></table>
    </div>
  </div>
  {% endif %}

  {% if logs %}
  <div class="section">
    <h2>10. Route Detail Table</h2>
    <div class="section-body">
      <table>
        <thead><tr><th>Stop #</th><th>Status</th><th>Plant</th><th>Arrive</th><th>Depart</th><th>Cargo Out</th><th>Notes</th></tr></thead>
        <tbody>
          {% for row in route_state.rows %}
            {
```

### 451. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_reviews.html:10`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
.container.mt-4.fade-in { max-width:none; margin:0 !important; padding:0 !important; animation:none; opacity:1; }

  *, *::before, *::after { box-sizing:border-box; }

  .mc { min-height:100vh; width:100%; display:flex; background:#f8fafc; color:#0f172a;
        font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif; }

  /* Sidebar */
  .mc-side { width:256px; flex:0 0 256px; background:#0f172a; color:#cbd5e1;
```

### 452. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_reviews.html:40`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
weight:800; margin:0; }
  .u-role { color:#475569; font-size:.68rem; margin:2px 0 0; }

  /* Main */
  .mc-main { flex:1; min-width:0; display:flex; flex-direction:column; height:100vh; overflow:hidden; }
  .mc-header { background:#fff; border-bottom:1px solid #e2e8f0; padding:16px 28px;
               display:flex; align-items:center; justify-content:space-between; gap:14px;
               z-index:10; box-shadow:0 1px 2px rgba(15,23,42
```

### 453. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_reviews.html:49`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
px; }
  .mc-body { flex:1; overflow-y:auto; padding:22px 28px; display:flex; flex-direction:column; gap:18px; }

  /* KPI */
  .kpi-row { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; }
  .kpi { background:#fff; border:1px solid #e2e8f0; border-radius:10px;
         padding:12px 14px; box-shadow:0 1px 2px rgba(15,23,42,.04); text-decoration:none; display:block; }
  .kpi.blue  { background:#eff6ff; border-color:#
```

### 454. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_reviews.html:52`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
x solid #e2e8f0; border-radius:10px;
         padding:12px 14px; box-shadow:0 1px 2px rgba(15,23,42,.04); text-decoration:none; display:block; }
  .kpi.blue  { background:#eff6ff; border-color:#bfdbfe; }
  .kpi.danger { background:#fff1f2; border-color:#fecdd3; }
  .kpi-lbl { font-size:.64rem; font-weight:900; text-transform:uppercase;
             letter-spacing:.07em; color:#64748b; margin:0 0 5px; }
  .kpi.blue  .kpi-lbl { color:#256
```

### 455. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_reviews.html:65`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
background:#e2e8f0; color:#334155; white-space:nowrap; }
  .kpi.blue  .kpi-tag { background:#bfdbfe; color:#1d4ed8; }
  .kpi.danger .kpi-tag { background:#ffe4e6; color:#be123c; }

  /* Panel */
  .panel { background:#fff; border:1px solid #e2e8f0; border-radius:18px;
           box-shadow:0 1px 2px rgba(15,23,42,.04); overflow:hidden; }
  .panel-top { padding:14px 20px; border-bottom:1px solid #e2e8f0; background:#f8fafc;
```

### 456. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_reviews.html:67`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
anel */
  .panel { background:#fff; border:1px solid #e2e8f0; border-radius:18px;
           box-shadow:0 1px 2px rgba(15,23,42,.04); overflow:hidden; }
  .panel-top { padding:14px 20px; border-bottom:1px solid #e2e8f0; background:#f8fafc;
               display:flex; align-items:center; justify-content:space-between;
               gap:12px; flex-wrap:wrap; }
  .panel-top h3 { font-size:.95rem; font-weight:900; color:#0f172a; margin:0;
```

### 457. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_reviews.html:81`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
table.dtbl th { padding:11px 14px; text-align:left; font-size:.63rem; font-weight:900;
                  text-transform:uppercase; letter-spacing:.07em; color:#64748b;
                  border-bottom:1px solid #e2e8f0; background:#f8fafc; white-space:nowrap; }
  table.dtbl th:last-child { text-align:right; }
  table.dtbl td { padding:13px 14px; border-bottom:1px solid #f1f5f9; vertical-align:middle; }
  table.dtbl tbody tr:last-child t
```

### 458. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_reviews.html:101`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
transition:background .15s; white-space:nowrap; }
  .btn-create:hover { background:#1d4ed8; }
  .resolve-form { display:flex; gap:8px; align-items:center; justify-content:flex-end; flex-wrap:nowrap; }
  .resolve-note { background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px;
                  padding:8px 11px; font-size:.8rem; color:#334155; outline:none; font-family:inherit; width:170px; }
  .resolve-note:focus { border-color
```

### 459. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_reviews.html:103`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
:#f8fafc; border:1px solid #e2e8f0; border-radius:10px;
                  padding:8px 11px; font-size:.8rem; color:#334155; outline:none; font-family:inherit; width:170px; }
  .resolve-note:focus { border-color:#93c5fd; background:#fff; box-shadow:0 0 0 3px rgba(147,197,253,.2); }

  @media (max-width:960px) {
    .mc-side { display:none; }
    .kpi-row { grid-template-columns:1fr; }
    .mc-header { padding:13px 16px; flex-wrap:wrap; }
```

### 460. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_reviews.html:78`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: default table look.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
olor:#64748b; }
  .text-sm { font-size:.72rem; line-height:1.25; }
  .text-muted { color:#64748b !important; }

  /* Table */
  .tbl-wrap { overflow-x:auto; -webkit-overflow-scrolling:touch; }
  table.dtbl { width:100%; border-collapse:collapse; min-width:760px; }
  table.dtbl th { padding:11px 14px; text-align:left; font-size:.63rem; font-weight:900;
                  text-transform:uppercase; letter-spacing:.07em; color:#64748b;
```

### 461. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_reviews.html:232`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: default table look.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
Stops Awaiting Manager Review
          </h3>
          <span class="text-sm text-muted">Driver flagged these stops with “Send to manager review”.</span>
        </div>
        <div class="tbl-wrap">
          <table class="dtbl">
            <thead>
              <tr>
                <th>Stop</th>
                <th>Reason</th>
                <th>Cargo (Arrived &rarr; Departed)</th>
                <th>Requested By</th>
```

### 462. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager_reviews.html:281`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: default table look.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
Driver-Closed Issue Closeouts
          </h3>
          <span class="text-sm text-muted">Issues drivers closed to continue when no manager was present.</span>
        </div>
        <div class="tbl-wrap">
          <table class="dtbl">
            <thead>
              <tr>
                <th>Stop</th>
                <th>Closeout Reason</th>
                <th>Closed By</th>
                <th>Closed</th>
                <th>Au
```

### 463. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager/move_requests.html:7`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
ay { display:none !important; }
  body.mgr-active .container.mt-4.fade-in { max-width:none; margin:0 !important; padding:0 !important; animation:none; opacity:1; }
  body.mgr-active { overflow-x:hidden; overflow-y:auto; background:#f8fafc; }
  .mq-shell { min-height:100vh; width:100%; display:flex; background:#f8fafc; color:#0f172a; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif; }
  .mq-side { width:236px;
```

### 464. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager/move_requests.html:8`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
width:none; margin:0 !important; padding:0 !important; animation:none; opacity:1; }
  body.mgr-active { overflow-x:hidden; overflow-y:auto; background:#f8fafc; }
  .mq-shell { min-height:100vh; width:100%; display:flex; background:#f8fafc; color:#0f172a; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif; }
  .mq-side { width:236px; flex:0 0 236px; height:100vh; position:sticky; top:0; overflow-y:auto; backgrou
```

### 465. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager/move_requests.html:18`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
hover:not(.active) { background:rgba(148,163,184,.1); color:#e2e8f0; }
  .mq-main { flex:1 1 auto; min-width:0; min-height:100vh; display:flex; flex-direction:column; }
  .mq-topbar { position:sticky; top:0; z-index:10; background:#fff; border-bottom:1px solid #e2e8f0; padding:16px 28px; display:flex; justify-content:space-between; gap:14px; align-items:flex-start; flex-wrap:wrap; box-shadow:0 1px 2px rgba(15,23,42,.04); }
  .mq-body {
```

### 466. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager/move_requests.html:25`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
lay:flex; gap:.5rem; flex-wrap:wrap; margin-bottom:1rem; }
  .queue-filter a { border:1px solid #cbd5e1; border-radius:999px; padding:.45rem .8rem; text-decoration:none; color:#334155; font-weight:800; font-size:.85rem; background:#fff; }
  .queue-filter a.active { background:#0f172a; color:#fff; border-color:#0f172a; }
  .queue-table { background:#fff; border:1px solid #e2e8f0; border-radius:12px; overflow:auto; max-width:100%; -webkit
```

### 467. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager/move_requests.html:27`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
999px; padding:.45rem .8rem; text-decoration:none; color:#334155; font-weight:800; font-size:.85rem; background:#fff; }
  .queue-filter a.active { background:#0f172a; color:#fff; border-color:#0f172a; }
  .queue-table { background:#fff; border:1px solid #e2e8f0; border-radius:12px; overflow:auto; max-width:100%; -webkit-overflow-scrolling:touch; }
  .queue-table table { margin:0; min-width:1180px; }
  .queue-table th { font-size:.72rem;
```

### 468. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager/move_requests.html:29`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
verflow:auto; max-width:100%; -webkit-overflow-scrolling:touch; }
  .queue-table table { margin:0; min-width:1180px; }
  .queue-table th { font-size:.72rem; text-transform:uppercase; letter-spacing:.05em; color:#64748b; background:#f8fafc; white-space:nowrap; }
  .queue-table td { vertical-align:top; font-size:.86rem; overflow-wrap:anywhere; }
  .request-summary { min-width:220px; max-width:360px; white-space:normal; color:#334155; line
```

### 469. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager/move_requests.html:103`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: default table look.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
ove_requests', status=selected_status) }}">Destination: {{ destination_filter }} x</a>{% endif %}
        </div>
      {% endif %}

<div class="queue-table table-responsive" aria-label="Scrollable move request queue">
  <table class="table table-hover align-middle">
    <thead>
      <tr>
        <th>Request #</th>
        <th>Source</th>
        <th>Original Request</th>
        <th>Requested By</th>
        <th>Requested Time</th>
```

### 470. NEEDS REVIEW — visual baseline screenshot checklist

**Location:** `templates/manager/move_request_form.html:8`
**Expected:** Manager/driver workflow pages should not reintroduce old white/maroon/default CSS unless intentionally scoped.
**Actual:** Potential visual drift: white page background.
**Recommendation:** Capture before/after screenshots. Move old styling behind an explicit legacy route or convert to current design tokens.

```text
s:flex-start; flex-wrap:wrap; margin-bottom:1rem; }
  .request-form-head h1 { margin:0; font-size:1.55rem; font-weight:900; color:#0f172a; }
  .request-form-head p { margin:.25rem 0 0; color:#64748b; }
  .request-card { background:#fff; border:1px solid #e2e8f0; border-radius:14px; padding:1rem; margin-bottom:1rem; }
  .request-card h2 { font-size:1rem; font-weight:900; margin:0 0 .8rem; color:#0f172a; }
  .field-grid { display:grid; gr
```

### 471. NEEDS REVIEW — mobile vs widescreen scope check

**Location:** `app/blueprints/driver/routes.py`
**Expected:** Driver mobile should remain focused on route actions, stops, proof, inspections, and end-of-day.
**Actual:** Driver/mobile file contains manager/widescreen concepts.
**Recommendation:** Verify role separation and remove manager-only controls from driver pages.

### 472. NEEDS REVIEW — mobile vs widescreen scope check

**Location:** `templates/driver_logs.html`
**Expected:** Driver mobile should remain focused on route actions, stops, proof, inspections, and end-of-day.
**Actual:** Driver/mobile file contains manager/widescreen concepts.
**Recommendation:** Verify role separation and remove manager-only controls from driver pages.

### 473. NEEDS REVIEW — mobile vs widescreen scope check

**Location:** `templates/manager_all_pretrips.html`
**Expected:** Manager/widescreen pages should retain driver/move/route operational context.
**Actual:** Manager/operations file may lack driver/route/move context.
**Recommendation:** Confirm manager pages still show operational flow, driver movements, and reviewable records.

### 474. NEEDS REVIEW — mobile vs widescreen scope check

**Location:** `templates/manager_tasks.html`
**Expected:** Manager/widescreen pages should retain driver/move/route operational context.
**Actual:** Manager/operations file may lack driver/route/move context.
**Recommendation:** Confirm manager pages still show operational flow, driver movements, and reviewable records.

### 475. NEEDS REVIEW — mobile vs widescreen scope check

**Location:** `templates/view_driver_log.html`
**Expected:** Driver mobile should remain focused on route actions, stops, proof, inspections, and end-of-day.
**Actual:** Driver/mobile file contains manager/widescreen concepts.
**Recommendation:** Verify role separation and remove manager-only controls from driver pages.

### 476. NEEDS REVIEW — mobile vs widescreen scope check

**Location:** `templates/_driver_log_photo_upload.html`
**Expected:** Driver mobile should remain focused on route actions, stops, proof, inspections, and end-of-day.
**Actual:** Driver/mobile file contains manager/widescreen concepts.
**Recommendation:** Verify role separation and remove manager-only controls from driver pages.

### 477. NEEDS REVIEW — mobile vs widescreen scope check

**Location:** `templates/depart_driver_log.html`
**Expected:** Driver mobile should remain focused on route actions, stops, proof, inspections, and end-of-day.
**Actual:** Driver/mobile file contains manager/widescreen concepts.
**Recommendation:** Verify role separation and remove manager-only controls from driver pages.

### 478. NEEDS REVIEW — mobile vs widescreen scope check

**Location:** `templates/partials/_floor_operations_snapshot.html`
**Expected:** Manager/widescreen pages should retain driver/move/route operational context.
**Actual:** Manager/operations file may lack driver/route/move context.
**Recommendation:** Confirm manager pages still show operational flow, driver movements, and reviewable records.

### 479. PASS — route inventory

**Expected:** Config should define routes/probes for browser smoke checks.
**Actual:** Loaded 17 configured routes/probes.
**Recommendation:** Run browser_smoke_audit.py against a live app for route status, redirects, and screenshots.
