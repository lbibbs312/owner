from django.http import HttpResponse
from django.shortcuts import render


def homepage(request):
    return render(request, "public_site/home.html")


def healthz(request):
    return HttpResponse("ok", content_type="text/plain")


def contact(request):
    return render(
        request,
        "public_site/static_page.html",
        {
            "page_title": "Contact",
            "lede": "For account, billing, or product questions, contact MoveDefense support.",
            "body": "Support intake will be connected during the Django v2 migration.",
        },
    )


def terms(request):
    return render(
        request,
        "public_site/static_page.html",
        {
            "page_title": "Terms",
            "lede": "MoveDefense service terms placeholder.",
            "body": "The full terms will be ported from the current production policy before launch.",
        },
    )


def privacy(request):
    return render(
        request,
        "public_site/static_page.html",
        {
            "page_title": "Privacy",
            "lede": "MoveDefense privacy placeholder.",
            "body": "The full privacy notice will be ported from the current production policy before launch.",
        },
    )
