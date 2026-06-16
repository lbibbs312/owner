import json
import re
import sys
from types import SimpleNamespace
from html import unescape

import pytest


@pytest.fixture()
def app(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    from app import create_app
    from app.extensions import db

    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def _visible_text(html):
    html = unescape(html)
    html = re.sub(r"<style\b[^>]*>.*?</style>", " ", html, flags=re.I | re.S)
    html = re.sub(r"<script\b[^>]*>.*?</script>", " ", html, flags=re.I | re.S)
    html = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", html).strip()
    return re.sub(r"\s+([.,;:!?])", r"\1", text)


def _allow_registration(client, **overrides):
    checkout = {
        "session_id": "cs_test_verified",
        "plan_key": "solo-driver",
        "plan_name": "Solo Driver",
        "customer": "cus_test",
        "customer_email": "",
    }
    checkout.update(overrides)
    with client.session_transaction() as sess:
        sess["registration_checkout"] = checkout


def test_welcome_page_serves_driver_logger_app(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-cache, max-age=0, must-revalidate"
    body = response.get_data(as_text=True)

    for expected in (
        "MoveDefense",
        "Driver Activity Log",
        "Driver activity log",
        "Create account",
        "Login with Google",
        "Forgot password?",
        "Driver account",
        "Private driver access",
        "Protect trip logs, fuel records, receipts, and exports",
        "Checking password",
        "Creating account",
        "Fuel record detected",
        "Fuel log",
        "Trip log",
        "Trip date",
        "Fuel date",
        "Save fuel PDF",
        "PPG needs gallons + cost",
        "MPG needs gallons",
        "Tank gauge after stop",
        "Fuel locations",
        "Records by stop",
        "Receipts uploaded",
        "gas_station",
        "Record first stop",
        "window.MOVEDEFENSE_CONFIG",
        "googleMapsApiKey",
        "googleClientId",
        "/api/account/login",
        "/api/account/register",
        "/api/driver-state",
        "/api/driver-day-state",
        "movedefense.viewDate.v1",
        "setViewDate",
        "stopsForDate(selectedDateKey)",
        "No fuel records logged for this date",
        "overscroll-behavior:none",
        "installAppHistoryGuard",
        "handleAppBackGesture",
        "serverSessionUnavailable=true;",
    ):
        assert expected in body
    for legacy in (
        "Driver paperwork into clean packets.",
        "MoveDefense Operations",
        "Manager Dispatch",
        "Production dispatch app",
        "Small Fleet",
        "Fleet Office",
        "View pricing",
        "Choose a paid plan",
        "workflow-route-board.jpg",
        "Replay intro",
        "Offline ready",
        "offline",
        "local account",
        "No local account",
        "on-device",
        "this device",
        "Old driver/admin logins",
        "configured Google client ID",
        "Google Identity Services",
        "you@example.com",
        "lbibbs312",
        "lbibbs322",
    ):
        assert legacy not in body


def test_welcome_page_renders_without_optional_bulletins(client, monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError

    from app.blueprints.public import routes as public_routes

    class BrokenTimestamp:
        @staticmethod
        def desc():
            return "created_at desc"

    class BrokenQuery:
        def order_by(self, *_args, **_kwargs):
            raise SQLAlchemyError("missing optional announcement table")

    monkeypatch.setattr(
        public_routes,
        "Announcement",
        SimpleNamespace(query=BrokenQuery(), created_at=BrokenTimestamp()),
    )

    response = client.get("/")

    assert response.status_code == 200
    assert "Driver Activity Log" in response.get_data(as_text=True)


def test_welcome_page_does_not_embed_marketing_checkout_forms(client):
    response = client.get("/")

    assert response.status_code == 200
    body = response.get_data(as_text=True)

    assert "/billing/checkout/" not in body
    assert 'action="/register"' not in body
    assert 'href="/register"' not in body


def test_install_app_page_is_sms_share_first(client):
    response = client.get("/app")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Share install link" in body
    assert "sms:?body=https%3A%2F%2Fmovedefense.com%2Fapp" in body
    assert "https://movedefense.com/app" in body
    assert "message shows an official site link instead of a file attachment" in body
    assert "Download Android installer" in body
    assert "MoveDefense.apk" in body
    assert "Installer verification" in body
    assert "Install MoveDefense from the official site" not in body
    assert "Download for Android" not in body


def test_one_driver_api_registers_and_persists_state(client, app):
    response = client.post(
        "/api/account/register",
        json={
            "email": "sync-driver@example.com",
            "password": "password123",
            "name": "Sync Driver",
        },
    )

    assert response.status_code == 201
    account = response.get_json()
    assert account["ok"] is True
    assert account["user"]["email"] == "sync-driver@example.com"
    assert account["state"]["exists"] is False

    state = {
        "driver": {"name": "Sync Driver", "license": "Freight & haul mode"},
        "logNumber": "MD-2026-001",
        "settings": {"mode": "freight", "truckMode": True, "chosen": True},
        "position": "idle",
        "stops": [
            {
                "id": "stop1",
                "sequence": 1,
                "arrival_time": 1781577600000,
                "location": {"business_name": "Receiver Dock", "address": "100 Test Ave"},
            }
        ],
    }
    day_state = {
        **state,
        "day_key": "2026-06-16",
        "stops": [{**state["stops"][0], "day_key": "2026-06-16"}],
    }
    saved = client.post(
        "/api/driver-state",
        json={"data": state, "day_states": {"2026-06-16": day_state}},
    )

    assert saved.status_code == 200
    assert saved.get_json()["state"]["data"]["logNumber"] == "MD-2026-001"

    with app.app_context():
        from app.models import DriverDayState, DriverState, User

        user = User.query.filter_by(email="sync-driver@example.com").first()
        record = DriverState.query.filter_by(user_id=user.id).first()
        day_record = DriverDayState.query.filter_by(
            user_id=user.id, day_key="2026-06-16"
        ).first()
        assert json.loads(record.data)["stops"][0]["location"]["business_name"] == "Receiver Dock"
        assert json.loads(day_record.data)["stops"][0]["day_key"] == "2026-06-16"

    day_payload = client.get("/api/driver-day-state?date=2026-06-16")

    assert day_payload.status_code == 200
    assert day_payload.get_json()["state"]["exists"] is True
    assert day_payload.get_json()["state"]["data"]["stops"][0]["location"]["business_name"] == "Receiver Dock"

    client.post("/api/account/logout")
    assert client.get("/api/driver-state").status_code == 401
    assert client.get("/api/driver-day-state?date=2026-06-16").status_code == 401

    login = client.post(
        "/api/account/login",
        json={"login": "sync-driver@example.com", "password": "password123"},
    )

    assert login.status_code == 200
    payload = login.get_json()
    assert payload["state"]["exists"] is True
    assert payload["state"]["data"]["stops"][0]["location"]["business_name"] == "Receiver Dock"


def test_one_driver_api_login_accepts_existing_driver_username(client, app):
    with app.app_context():
        from app.extensions import db
        from app.models import User

        user = User(username="lbibbs312", email="lbibbs312@example.com", role="driver")
        user.set_password("0000")
        db.session.add(user)
        db.session.commit()

    response = client.post(
        "/api/account/login",
        json={"login": "lbibbs312", "password": "0000"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["user"]["username"] == "lbibbs312"


def test_billing_checkout_fails_closed_until_stripe_is_configured(client, app):
    app.config.update(
        STRIPE_SECRET_KEY="",
        STRIPE_PRICE_OWNER_OPERATOR="",
    )

    response = client.post("/billing/checkout/owner-operator")

    assert response.status_code == 503
    text = _visible_text(response.get_data(as_text=True))
    assert "Checkout unavailable" in text
    assert "Checkout not configured" in text
    assert "Owner-Operator" in text
    assert "$49/month" in text


def test_billing_checkout_creates_stripe_session_and_redirects(client, app, monkeypatch):
    created = {}

    class FakeSession:
        @staticmethod
        def create(**params):
            created.update(params)
            return {"url": "https://checkout.stripe.test/session"}

    fake_stripe = SimpleNamespace(
        api_key=None,
        api_version=None,
        checkout=SimpleNamespace(Session=FakeSession),
    )
    monkeypatch.setitem(sys.modules, "stripe", fake_stripe)
    app.config.update(
        PUBLIC_BASE_URL="https://movedefense.test",
        STRIPE_SECRET_KEY="sk_test_configured",
        STRIPE_API_VERSION="2026-05-27.dahlia",
        STRIPE_PRICE_OWNER_OPERATOR="price_owner_operator",
        STRIPE_ALLOW_PROMOTION_CODES=True,
        STRIPE_AUTOMATIC_TAX=True,
    )

    response = client.post("/billing/checkout/owner-operator")

    assert response.status_code == 303
    assert response.headers["Location"] == "https://checkout.stripe.test/session"
    assert fake_stripe.api_key == "sk_test_configured"
    assert fake_stripe.api_version == "2026-05-27.dahlia"
    assert created["mode"] == "subscription"
    assert created["line_items"] == [{"price": "price_owner_operator", "quantity": 1}]
    assert created["success_url"] == "https://movedefense.test/billing/success?session_id={CHECKOUT_SESSION_ID}"
    assert created["cancel_url"] == "https://movedefense.test/billing/cancel?plan=owner-operator"
    assert created["metadata"]["billing_plan"] == "owner-operator"
    assert created["allow_promotion_codes"] is True
    assert created["automatic_tax"] == {"enabled": True}


def test_billing_success_verifies_checkout_before_registration(client, app, monkeypatch):
    class FakeSession:
        @staticmethod
        def retrieve(session_id):
            return {
                "id": session_id,
                "status": "complete",
                "payment_status": "paid",
                "metadata": {"billing_plan": "owner-operator"},
                "customer": "cus_test",
                "customer_details": {"email": "buyer@example.com"},
            }

    fake_stripe = SimpleNamespace(
        api_key=None,
        api_version=None,
        checkout=SimpleNamespace(Session=FakeSession),
    )
    monkeypatch.setitem(sys.modules, "stripe", fake_stripe)
    app.config.update(
        STRIPE_SECRET_KEY="sk_test_configured",
        STRIPE_API_VERSION="2026-05-27.dahlia",
    )

    response = client.get("/billing/success?session_id=cs_test_complete")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/register")
    with client.session_transaction() as sess:
        checkout = sess["registration_checkout"]
    assert checkout["session_id"] == "cs_test_complete"
    assert checkout["plan_key"] == "owner-operator"
    assert checkout["customer_email"] == "buyer@example.com"


def test_billing_success_blocks_unverified_checkout(client, app, monkeypatch):
    class FakeSession:
        @staticmethod
        def retrieve(session_id):
            return {
                "id": session_id,
                "status": "open",
                "payment_status": "unpaid",
                "metadata": {"billing_plan": "owner-operator"},
            }

    fake_stripe = SimpleNamespace(
        api_key=None,
        api_version=None,
        checkout=SimpleNamespace(Session=FakeSession),
    )
    monkeypatch.setitem(sys.modules, "stripe", fake_stripe)
    app.config.update(STRIPE_SECRET_KEY="sk_test_configured")

    response = client.get("/billing/success?session_id=cs_test_open")

    assert response.status_code == 403
    text = _visible_text(response.get_data(as_text=True))
    assert "Checkout not verified" in text
    assert "Account setup blocked" in text
    with client.session_transaction() as sess:
        assert "registration_checkout" not in sess


def test_welcome_page_uses_safe_product_language(client):
    response = client.get("/")

    assert response.status_code == 200
    text = _visible_text(response.get_data(as_text=True))
    lower_text = text.lower()

    assert "MoveDefense" in text
    assert "Driver activity log" in text
    assert "Not an ELD" in text
    assert "No duty status" in text
    assert "hours-of-service" in lower_text
    for banned in (
        "critical",
        "exception",
        "gap",
        "warning",
        "FCSMA",
        "DOT approved",
        "FMCSA certified",
        "guaranteed compliant",
    ):
        assert banned.lower() not in lower_text


def test_privacy_notice_is_public_plain_language_and_standalone(client):
    response = client.get("/privacy")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    text = _visible_text(body)
    lower_text = text.lower()

    assert "MoveDefense Privacy Notice" in text
    for section in (
        "Who operates MoveDefense",
        "Information we collect",
        "Route, stop, and driver records",
        "Reports, inspections, and fuel records",
        "Documents and photos",
        "Restricted documents",
        "How we use information",
        "Who can access information",
        "Service providers",
        "Cookies and session data",
        "How long records are kept",
        "User choices and requests",
        "Children\u2019s privacy",
        "Changes to this notice",
        "Contact",
    ):
        assert section in text
    assert (
        "MoveDefense is used to create route, stop, report, document, and route packet records. "
        "Uploaded documents and photos are stored with the related route, stop, truck, driver, "
        "or report and are visible to authorized users."
    ) in text
    assert (
        "Restricted documents, such as driver credentials, DOT cards, licenses, insurance, "
        "registration, or medical documents, should only be uploaded when required by the "
        "company or account administrator. These records should be limited to authorized users."
    ) in text
    assert "MoveDefense is not intended for children under 13." in text
    assert "Privacy contact: bibbstechnology@gmail.com" in text
    assert "md-shell" not in body
    assert "md-driver-bottom-nav" not in body
    assert "navbar" not in body
    assert "audit" not in lower_text
    assert not re.search(r"\bai\b", lower_text)
    assert not re.search(r"\bocr\b", lower_text)
    assert "ssn" not in lower_text
    assert "social security" not in lower_text


@pytest.mark.parametrize("path", ["/", "/login", "/privacy", "/terms"])
def test_public_and_auth_pages_include_public_footer_links(client, path):
    response = client.get(path)

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    text = _visible_text(body)

    assert 'href="/privacy"' in body
    assert 'href="/terms"' in body
    assert 'href="/contact"' in body
    assert "Privacy \u00b7 Terms \u00b7 Contact" in text


def test_register_page_links_terms_and_privacy_notice(client):
    _allow_registration(client)

    response = client.get("/register")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    text = _visible_text(body)

    assert "By creating an account, you agree to the Terms and acknowledge the Privacy Notice." in text
    assert 'href="/terms"' in body
    assert 'href="/privacy"' in body
    assert "Management" not in text
    assert "Manager PIN" not in text


def test_direct_register_is_blocked_until_checkout_is_verified(client):
    response = client.get("/register", follow_redirects=False)

    assert response.status_code == 403
    text = _visible_text(response.get_data(as_text=True))
    assert "Checkout required" in text
    assert "Account setup blocked" in text


def test_terms_page_is_public_plain_language_and_not_placeholder(client):
    response = client.get("/terms")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    text = _visible_text(body)
    lower_text = text.lower()

    assert "MoveDefense Terms of Use" in text
    assert "Effective date: June 6, 2026" in text
    for section in (
        "Use of MoveDefense",
        "Accounts and access",
        "Driver, route, report, and document records",
        "Uploaded files and photos",
        "Customer/company responsibility",
        "Acceptable use",
        "No legal, tax, insurance, or safety compliance advice",
        "Service changes and availability",
        "Contact",
    ):
        assert section in text
    assert "Questions about these terms can be sent to bibbstechnology@gmail.com." in text
    assert 'href="mailto:bibbstechnology@gmail.com"' in body
    assert "placeholder" not in lower_text
    assert "coming soon" not in lower_text
    assert "will be published later" not in lower_text
    assert "will be published here" not in lower_text
    assert "audit" not in lower_text
    assert "md-shell" not in body
    assert "md-driver-bottom-nav" not in body
    assert "navbar" not in body


def test_contact_page_is_public_and_production_ready(client):
    response = client.get("/contact")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    text = _visible_text(body)
    assert "MoveDefense Contact" in text
    assert "bibbstechnology@gmail.com" in text
    assert 'href="mailto:bibbstechnology@gmail.com"' in body
    assert "placeholder" not in text.lower()


def test_daily_route_pass_checkout_creates_payment_session(client, app, monkeypatch):
    """The Daily Route Pass is now wired in config and creates a one-time payment session."""
    created = {}

    class FakeSession:
        @staticmethod
        def create(**params):
            created.update(params)
            return {"url": "https://checkout.stripe.test/daily-route-pass"}

    fake_stripe = SimpleNamespace(
        api_key=None,
        api_version=None,
        checkout=SimpleNamespace(Session=FakeSession),
    )
    monkeypatch.setitem(sys.modules, "stripe", fake_stripe)
    app.config.update(
        PUBLIC_BASE_URL="https://movedefense.test",
        STRIPE_SECRET_KEY="sk_test_configured",
        STRIPE_PRICE_DAILY_ROUTE_PASS="price_daily_route_pass",
    )

    from app.services.stripe_checkout import configured_billing_plan_keys

    # Regression: the price env was missing from config so this plan could never configure.
    assert "daily-route-pass" in configured_billing_plan_keys(app.config)

    response = client.post("/billing/checkout/daily-route-pass")
    assert response.status_code == 303
    assert response.headers["Location"] == "https://checkout.stripe.test/daily-route-pass"
    assert created["mode"] == "payment"
    assert created["line_items"] == [{"price": "price_daily_route_pass", "quantity": 1}]
    assert created["metadata"]["billing_plan"] == "daily-route-pass"
