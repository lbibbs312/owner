import re
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


@pytest.mark.parametrize("path", ["/", "/login", "/register", "/privacy"])
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

    assert "By creating an account, you acknowledge the Privacy Notice." in text
    assert "agree to the Terms" not in text
    assert 'href="/privacy"' in body


def test_terms_placeholder_is_public_and_not_an_agreement_page(client):
    response = client.get("/terms")

    assert response.status_code == 200
    text = _visible_text(response.get_data(as_text=True))
    assert "MoveDefense Terms" in text
    assert "placeholder" in text.lower()
    assert "legal agreement page" in text.lower()


def test_contact_page_is_public_and_production_ready(client):
    response = client.get("/contact")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    text = _visible_text(body)
    assert "MoveDefense Contact" in text
    assert "bibbstechnology@gmail.com" in text
    assert 'href="mailto:bibbstechnology@gmail.com"' in body
    assert "placeholder" not in text.lower()
