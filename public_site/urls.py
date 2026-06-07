from django.urls import path

from . import views

app_name = "public_site"

urlpatterns = [
    path("", views.homepage, name="home"),
    path("healthz/", views.healthz, name="healthz"),
    path("contact/", views.contact, name="contact"),
    path("terms/", views.terms, name="terms"),
    path("privacy/", views.privacy, name="privacy"),
]
