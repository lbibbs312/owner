import importlib
import importlib.util
import os
from collections.abc import Mapping

import pytest


DJANGO_SETTINGS_MODULE = "movedefense_django.settings"
HEALTH_URL_CANDIDATES = ("/health/", "/healthz/", "/healthz", "/up/")
EXPECTED_BILLING_PLAN_KEYS = {
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
}


def _django_scaffold_available() -> bool:
    try:
        return importlib.util.find_spec(DJANGO_SETTINGS_MODULE) is not None
    except ModuleNotFoundError:
        return False


@pytest.fixture(scope="session")
def django_ready():
    if not _django_scaffold_available():
        pytest.skip("Django v2 scaffold is not present in this checkout yet")

    import django
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", DJANGO_SETTINGS_MODULE)

    from django.apps import apps

    if not apps.ready:
        django.setup()
    return django


def test_django_v2_settings_import_and_system_check(django_ready):
    settings = importlib.import_module(DJANGO_SETTINGS_MODULE)

    assert settings.SECRET_KEY
    assert settings.ROOT_URLCONF
    assert "django.contrib.auth" in settings.INSTALLED_APPS

    from django.core.management import call_command

    call_command("check", fail_level="ERROR")


def test_django_v2_health_url_smoke(django_ready):
    from django.test import Client, override_settings

    client = Client()
    with override_settings(ALLOWED_HOSTS=["testserver", "localhost"]):
        responses = [(path, client.get(path)) for path in HEALTH_URL_CANDIDATES]

    ok_path, ok_response = next(
        ((path, response) for path, response in responses if response.status_code == 200),
        (None, None),
    )
    assert ok_path is not None, {
        path: response.status_code for path, response in responses
    }

    body = ok_response.content.decode("utf-8", errors="replace").lower()
    assert "ok" in body or "healthy" in body or ok_response.headers.get("content-type", "").startswith(
        "application/json"
    )


def test_django_v2_homepage_has_no_public_register_link_when_implemented(django_ready):
    from django.template import TemplateDoesNotExist
    from django.test import Client, override_settings

    client = Client()
    with override_settings(ALLOWED_HOSTS=["testserver", "localhost"]):
        try:
            response = client.get("/", follow=True)
        except TemplateDoesNotExist:
            pytest.skip("Django v2 homepage template is not implemented yet")

    if response.status_code == 404:
        pytest.skip("Django v2 homepage is not implemented yet")

    assert response.status_code == 200
    html = response.content.decode("utf-8", errors="replace").lower()
    assert 'href="/register"' not in html
    assert "href='/register'" not in html
    assert 'action="/register"' not in html
    assert "action='/register'" not in html
    assert ">management<" not in html
    assert "manager pin" not in html


def test_django_v2_billing_plan_registry_imports(django_ready):
    module = None
    import_errors = {}

    for module_name in (
        "billing.plans",
        "billing.registry",
        "movedefense_django.billing.plans",
        "movedefense_django.billing.registry",
    ):
        try:
            module = importlib.import_module(module_name)
            break
        except ImportError as exc:
            import_errors[module_name] = str(exc)

    assert module is not None, import_errors

    plans = getattr(module, "BILLING_PLANS", None)
    assert plans is not None

    if isinstance(plans, Mapping):
        plan_keys = set(plans)
    else:
        plan_keys = {getattr(plan, "key", None) for plan in plans}

    assert EXPECTED_BILLING_PLAN_KEYS <= plan_keys
