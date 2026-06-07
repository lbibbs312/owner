from django.contrib.auth import login as auth_login
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .forms import PublicDriverRegistrationForm, REGISTRATION_CHECKOUT_SESSION_KEY


class AccountLoginView(LoginView):
    template_name = "accounts/login.html"
    redirect_authenticated_user = True


login_view = AccountLoginView.as_view()


def _registration_checkout(request):
    checkout = request.session.get(REGISTRATION_CHECKOUT_SESSION_KEY)
    if not isinstance(checkout, dict):
        return None
    if not checkout.get("session_id") or not checkout.get("plan_key"):
        return None
    return checkout


@require_http_methods(["GET", "POST"])
def register_view(request):
    checkout = _registration_checkout(request)
    if not checkout:
        return render(
            request,
            "accounts/checkout_required.html",
            status=403,
        )

    if request.method == "POST":
        form = PublicDriverRegistrationForm(request.POST, checkout=checkout)
        if form.is_valid():
            user = form.save()
            request.session.pop(REGISTRATION_CHECKOUT_SESSION_KEY, None)
            auth_login(request, user)
            return redirect("/")
    else:
        form = PublicDriverRegistrationForm(checkout=checkout)

    return render(
        request,
        "accounts/register.html",
        {
            "checkout": checkout,
            "form": form,
        },
    )
