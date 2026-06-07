"""URL routing for the MoveDefense Django v2 scaffold."""

from __future__ import annotations

import importlib.util

from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def health(request):
    return JsonResponse({"status": "ok", "service": "movedefense-django-v2"})


def _module_exists(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health, name="health"),
]

if _module_exists("accounts.urls"):
    urlpatterns.append(path("accounts/", include("accounts.urls")))

if _module_exists("billing.urls"):
    urlpatterns.append(path("billing/", include("billing.urls")))

if _module_exists("public_site.urls"):
    urlpatterns.append(path("", include("public_site.urls")))
else:
    urlpatterns.append(path("", health, name="home"))
