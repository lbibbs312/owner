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


def test_welcome_page_positions_packets_and_pricing(client):
    response = client.get("/")

    assert response.status_code == 200
    text = _visible_text(response.get_data(as_text=True))

    assert "Turn driver paperwork into clean route, incident, and IFTA support packets." in text
    assert "We help owner-operators and small fleets" in text
    assert "Preview packets" in text
    assert "Start free" in text
    assert "Set up small fleet" in text
    assert "Free Preview" in text
    assert "Solo Driver" in text
    assert "Owner-Operator" in text
    assert "Small Fleet" in text
    assert "Fleet Office" in text
    assert "Includes up to 5 drivers or vehicles" in text
    assert "$15/month per extra driver or vehicle" in text
    assert "MoveDefense Paperwork Cleanup" in text
    assert "starting at $299/month" in text


def test_welcome_page_posts_paid_items_to_billing_checkout(client):
    response = client.get("/")

    assert response.status_code == 200
    body = response.get_data(as_text=True)

    for plan_key in (
        "solo-driver",
        "owner-operator",
        "small-fleet",
        "fleet-office",
        "driver-forms-pack",
        "record-kit",
        "ifta-worksheet-bundle",
        "branded-packet-setup",
        "paper-form-conversion",
        "fleet-packet-setup",
    ):
        assert f'action="/billing/checkout/{plan_key}" method="POST"' in body
    assert 'action="/register" method="GET"' in body


def test_billing_checkout_fails_closed_until_stripe_is_configured(client):
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


def test_welcome_page_uses_safe_product_language(client):
    response = client.get("/")

    assert response.status_code == 200
    text = _visible_text(response.get_data(as_text=True))
    lower_text = text.lower()

    assert "MoveDefense" in text
    assert re.search(r"\bwe\b", lower_text)
    assert re.search(r"\bour\b", lower_text)
    assert not re.search(r"\b(i|my|me)\b", lower_text)
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
    assert "FMCSA-aligned" in text
    assert "DOT-ready recordkeeping" in text
    assert "insurance-ready packet" in lower_text
    assert "IFTA support worksheet" in text


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


@pytest.mark.parametrize("path", ["/", "/login", "/register", "/privacy", "/terms"])
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
    response = client.get("/register")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    text = _visible_text(body)

    assert "By creating an account, you agree to the Terms and acknowledge the Privacy Notice." in text
    assert 'href="/terms"' in body
    assert 'href="/privacy"' in body


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
