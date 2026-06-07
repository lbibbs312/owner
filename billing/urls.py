from django.urls import path

from . import views

app_name = "billing"

urlpatterns = [
    path("checkout/<slug:plan_key>/", views.checkout, name="checkout"),
    path("success/", views.success, name="success"),
    path("cancel/", views.cancel, name="cancel"),
    path("blocked/", views.blocked, name="blocked"),
]
