from django.db import models

# Create your models here.
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from django.contrib.auth.base_user import (
    AbstractBaseUser,
    BaseUserManager,
)

from django.contrib.auth.models import PermissionsMixin


class UserManager(BaseUserManager):

    def create_user(
        self,
        phone,
        username,
        full_name,
        password=None,
        **extra_fields
    ):

        if not phone:
            raise ValueError("Phone is required")

        if not username:
            raise ValueError("Username is required")

        if not full_name:
            raise ValueError("Full name is required")

        if not password:
            raise ValueError("Password is required")

        username = self.model.normalize_username(
            username.strip()
        )

        user = self.model(
            phone=phone,
            username=username,
            full_name=full_name.strip(),
            **extra_fields
        )

        user.set_password(password)

        user.save(using=self._db)

        return user


    def create_superuser(
        self,
        phone,
        username,
        full_name,
        password=None,
        **extra_fields
    ):

        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        extra_fields.setdefault("terms_version", "admin")
        extra_fields.setdefault("terms_accepted_at", timezone.now())

        return self.create_user(
            phone,
            username,
            full_name,
            password,
            **extra_fields
        )


class User(AbstractBaseUser, PermissionsMixin):

    id = models.BigAutoField(primary_key=True)

    phone = models.CharField(
        max_length=16,
        unique=True
    )

    username = models.CharField(
        max_length=30,
        unique=True
    )

    full_name = models.CharField(
        max_length=150
    )

    phone_verified_at = models.DateTimeField(
        null=True,
        blank=True
    )

    timezone = models.CharField(
        max_length=64,
        default="UTC"
    )

    locale = models.CharField(
        max_length=16,
        default="fa-IR"
    )

    terms_version = models.CharField(
        max_length=32
    )

    terms_accepted_at = models.DateTimeField()

    is_active = models.BooleanField(default=True)

    is_staff = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = "phone"

    REQUIRED_FIELDS = [
        "username",
        "full_name",
    ]

    class Meta:
        db_table = "users"

    def __str__(self):
        return self.phone


class OTPChallenge(models.Model):

    class Purpose(models.TextChoices):

        REGISTER = "register", "Register"

        LOGIN = "login", "Login"

        PASSWORD_RESET = "password_reset", "Password Reset"


    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="otp_challenges"
    )

    phone = models.CharField(max_length=16)

    purpose = models.CharField(
        max_length=32,
        choices=Purpose.choices
    )

    code_hash = models.CharField(max_length=128)

    expires_at = models.DateTimeField()

    verified_at = models.DateTimeField(
        null=True,
        blank=True
    )

    consumed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    attempt_count = models.PositiveSmallIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "otp_challenges"

        indexes = [
            models.Index(
                fields=["phone", "purpose", "created_at"],
                name="otp_phone_purpose_idx"
            )
        ]

    def __str__(self):
        return f"{self.phone} - {self.purpose}"