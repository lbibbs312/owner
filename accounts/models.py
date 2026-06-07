from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        DRIVER = "driver", "Driver"
        MANAGEMENT = "management", "Management"

    email = models.EmailField("email address", unique=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.DRIVER)
    employee_id = models.CharField(max_length=32, blank=True)
    department = models.CharField(max_length=64, blank=True)

    @property
    def display_name(self):
        name = " ".join(part for part in [self.first_name, self.last_name] if part)
        return name or self.username or self.email

    @property
    def is_driver(self):
        return self.role == self.Role.DRIVER

    @property
    def is_management(self):
        return self.role == self.Role.MANAGEMENT
