from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import User


REGISTRATION_CHECKOUT_SESSION_KEY = "registration_checkout"


class PublicDriverRegistrationForm(UserCreationForm):
    """Public signup is only opened by a verified checkout session."""

    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)
    employee_id = forms.CharField(max_length=32, required=False)
    department = forms.CharField(max_length=64, required=False)
    email = forms.EmailField()

    class Meta(UserCreationForm.Meta):
        model = User
        fields = (
            "username",
            "first_name",
            "last_name",
            "employee_id",
            "department",
            "email",
            "password1",
            "password2",
        )

    def __init__(self, *args, checkout=None, **kwargs):
        self.checkout = checkout or {}
        super().__init__(*args, **kwargs)
        checkout_email = self._checkout_email()
        if checkout_email and not self.is_bound:
            self.fields["email"].initial = checkout_email

    def _checkout_email(self):
        return (
            self.checkout.get("customer_email")
            or self.checkout.get("email")
            or ""
        ).strip().lower()

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        checkout_email = self._checkout_email()
        if checkout_email and email != checkout_email:
            raise forms.ValidationError(
                "Use the same email address from checkout to create this account."
            )
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account already exists with that email.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.DRIVER
        user.email = self.cleaned_data["email"]
        user.employee_id = self.cleaned_data.get("employee_id", "")
        user.department = self.cleaned_data.get("department", "")
        if commit:
            user.save()
        return user
