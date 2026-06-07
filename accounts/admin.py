from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (
        (
            "MoveDefense profile",
            {"fields": ("role", "employee_id", "department")},
        ),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        (
            "MoveDefense profile",
            {"fields": ("role", "employee_id", "department", "email")},
        ),
    )
    list_display = (
        "username",
        "email",
        "role",
        "employee_id",
        "department",
        "is_staff",
        "is_active",
    )
    list_filter = DjangoUserAdmin.list_filter + ("role", "department")
    search_fields = ("username", "email", "first_name", "last_name", "employee_id")
