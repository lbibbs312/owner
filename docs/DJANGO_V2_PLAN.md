# MoveDefense Django v2 Plan

This branch is a side-by-side Django v2 scaffold. The Flask app remains the live production app until every parity checkpoint below is proven against copied or staging data.

## Current Boundary

- Keep Flask deployable while Django v2 is built beside it.
- Do not import Flask app globals into Django request paths.
- Share only stable concepts at first: billing plan keys, route state vocabulary, role names, document/evidence labels, and environment-variable names.
- Django v2 owns new project structure, tests, and docs. Flask files stay unchanged unless a later checkpoint explicitly ports a feature.

## Dependency Choice

- Use `Django>=5.2,<6`.
- Django 5.2 is the current conservative target because it is an LTS release and supports the repo's Python range.
- Do not add Django REST Framework, Channels, Celery, or third-party admin packages during the scaffold phase.

## Phased Port

1. Scaffold: project settings, root URL config, health endpoint, environment loading, static/template paths, and a minimal homepage shell.
2. Accounts: custom user model, role choices, login/logout, driver-only registration after verified checkout, management users created only by admin or invite.
3. Billing: Stripe Checkout plan registry, checkout-session creation, verified success handoff, subscription/customer persistence, and fail-closed account creation.
4. Operations: driver route, pretrip, posttrip, service-stop, cargo, and route-finalization domain models.
5. Evidence: uploads, document numbers, route packets, print/PDF parity, immutable audit events, and proof summaries.
6. Manager workspace: dense dispatch board, route review, driver logs, issue details, move requests, and admin-only management workflows.
7. Realtime/update path: decide between plain polling, server-sent events, or Channels only after the manager/driver parity model is stable.
8. Cutover: run Django against staging data, compare generated records/packets with Flask, then switch Render only after parity is documented.

## Parity Checkpoints

- Public site has no standalone `/register` link or management signup option.
- Checkout is the only public path into account creation.
- Verified checkout creates only driver/customer-facing accounts.
- Management accounts require admin creation or an invite path.
- Driver mobile route CTA semantics match Flask: route finalize appears only after a completed posttrip or a manual finalize action.
- Service stops remain in the route timeline without cargo prompts when they are not load/unload work.
- Route reports are scoped to the selected route/date and do not pull unrelated history by shared metadata.
- Printed and PDF records use canonical stop summaries, saved signatures, and numbered document treatment.
- Manager pages keep summary-first operational readouts with detailed evidence below.
- Every non-OK badge has an explainable reason, evidence, and next action.

## Test Ownership

`tests/test_django_v2_scaffold.py` is the scaffold contract file. It skips while the Django scaffold is absent, then enforces:

- `movedefense_django.settings` imports and passes Django system checks.
- At least one health URL responds with HTTP 200.
- The Django homepage, when implemented, does not expose public registration or management signup.
- The Django billing plan registry imports and contains the same paid plan keys as the Flask public billing surface.

## Do Not Port Yet

- Do not move live SQLite or production data.
- Do not replace Flask auth/session behavior in production.
- Do not point Render at Django v2.
- Do not recreate the whole manager dashboard before route/account/billing parity is pinned.
- Do not introduce broad frontend redesign while backend parity is still being defined.
