# MoveDefense Agent Rules

Do not patch only the visible PDF/template bug.

Before changing behavior:
1. Find the source of truth.
2. Check whether the same logic exists elsewhere.
3. Add or update regression tests.
4. Run tests.
5. Regenerate affected PDFs/screens.
6. Confirm user-facing output matches acceptance examples.

Business rules:
- Current open stop is active work, not a critical exception.
- Missing PostTrip mileage is pending, not correction required.
- Only impossible or conflicting odometer math is correction required.
- Multi-stop cargo is normal when a driver drops one load and continues with another.
- Cargo review should explain approval status, not repeat the route table.
- Old scans must not appear unless linked to current route_id, stop_id, or driver_log_id.
- Photos uploaded in one workflow must render in every report that references them.
- Templates must not invent route/cargo/mileage meaning. Use shared services.

Definition of done:
- Relevant tests pass.
- No duplicated business logic introduced.
- No empty report sections.
- No contradictory report statements.
- Generated PDF is manually reviewed before final response.
