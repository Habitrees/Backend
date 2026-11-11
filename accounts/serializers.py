from django.contrib.auth.password_validation import (
    validate_password as django_validate_password
)

from rest_framework import serializers

from .models import User
from .phone_utils import normalize_phone
from django.core.exceptions import ValidationError as DjangoValidationError
from django.contrib.auth import authenticate


class RegisterSendOTPSerializer(serializers.Serializer):

    phone = serializers.CharField(max_length=32)

    def validate_phone(self, value):

        try:
            return normalize_phone(value)

        except ValueError:
            raise serializers.ValidationError(
                "شماره موبایل معتبر نیست."
            )


class RegisterVerifyOTPSerializer(serializers.Serializer):

    phone = serializers.CharField(max_length=32)

    code = serializers.RegexField(
        regex=r"^\d{6}$",
        error_messages={
            "invalid": "کد باید ۶ رقم باشد."
        }
    )

    username = serializers.CharField(
        min_length=3,
        max_length=30
    )

    full_name = serializers.CharField(
        max_length=150
    )

    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False
    )

    timezone = serializers.CharField(
        max_length=64,
        required=False,
        default="UTC"
    )

    locale = serializers.CharField(
        max_length=16,
        required=False,
        default="fa-IR"
    )

    terms_accepted = serializers.BooleanField(
        required=True
    )

    def validate_phone(self, value):

        try:
            return normalize_phone(value)

        except ValueError:
            raise serializers.ValidationError(
                "شماره موبایل معتبر نیست."
            )

    def validate_username(self, value):

        value = value.strip()

        if User.objects.filter(username=value).exists():

            raise serializers.ValidationError(
                "این نام کاربری قبلاً انتخاب شده است."
            )

        return value

    def validate_full_name(self, value):

        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "نام کامل الزامی است."
            )

        return value

    def validate(self, attrs):

        candidate_user = User(
            phone=attrs["phone"],
            username=attrs["username"],
            full_name=attrs["full_name"],
        )

        try:
            django_validate_password(
                attrs["password"],
                user=candidate_user,
            )

        except DjangoValidationError as exc:

            raise serializers.ValidationError({
                "password": exc.messages
            })

        return attrs

    def validate_terms_accepted(self, value):

        if not value:

            raise serializers.ValidationError(
                "پذیرش قوانین برای ثبت‌نام الزامی است."
            )

        return value
class LoginSerializer(serializers.Serializer):

    phone = serializers.CharField(
        max_length=32
    )

    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        style={"input_type": "password"}
    )

    def validate_phone(self, value):

        try:
            return normalize_phone(value)

        except ValueError:
            raise serializers.ValidationError(
                "شماره موبایل معتبر نیست."
            )

    def validate(self, attrs):

        user = authenticate(
            request=self.context.get("request"),
            phone=attrs["phone"],
            password=attrs["password"]
        )

        # Reject invalid credentials, inactive users,
        # and users whose phone has not been verified.
        if (
            user is None
            or not user.is_active
            or user.phone_verified_at is None
        ):

            raise serializers.ValidationError({
                "detail": "شماره موبایل یا رمز عبور صحیح نیست."
            })

        attrs["user"] = user

        return attrs

class OTPSendResponseSerializer(serializers.Serializer):

    detail = serializers.CharField()

    expires_in = serializers.IntegerField()

    resend_after = serializers.IntegerField()


class RegisterUserResponseSerializer(serializers.Serializer):

    id = serializers.IntegerField()

    phone = serializers.CharField()

    username = serializers.CharField()

    full_name = serializers.CharField()


class RegisterSuccessResponseSerializer(serializers.Serializer):

    detail = serializers.CharField()

    user = RegisterUserResponseSerializer()

    access = serializers.CharField()


class LoginUserResponseSerializer(serializers.Serializer):

    id = serializers.IntegerField()

    phone = serializers.CharField()

    username = serializers.CharField()

    full_name = serializers.CharField()


class LoginSuccessResponseSerializer(serializers.Serializer):

    detail = serializers.CharField()

    user = LoginUserResponseSerializer()

    access = serializers.CharField()




class PasswordResetSendOTPSerializer(serializers.Serializer):

    phone = serializers.CharField(max_length=32)

    def validate_phone(self, value):

        try:
            return normalize_phone(value)

        except ValueError:
            raise serializers.ValidationError(
                "شماره موبایل معتبر نیست."
            )


class PasswordResetConfirmSerializer(serializers.Serializer):

    phone = serializers.CharField(max_length=32)

    code = serializers.RegexField(
        regex=r"^[0-9]{6}$",
        error_messages={
            "invalid": "کد باید ۶ رقم باشد."
        }
    )

    new_password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        style={"input_type": "password"}
    )

    confirm_new_password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        style={"input_type": "password"}
    )

    def validate_phone(self, value):

        try:
            return normalize_phone(value)

        except ValueError:
            raise serializers.ValidationError(
                "شماره موبایل معتبر نیست."
            )

    def validate(self, attrs):

        if attrs["new_password"] != attrs["confirm_new_password"]:

            raise serializers.ValidationError({
                "confirm_new_password": (
                    "تکرار رمز عبور با رمز جدید مطابقت ندارد."
                )
            })

        return attrs


class PasswordResetConfirmResponseSerializer(serializers.Serializer):

    detail = serializers.CharField()



class PasswordResetVerifyOTPSerializer(serializers.Serializer):

    phone = serializers.CharField(max_length=32)

    code = serializers.RegexField(
        regex=r"^\d{6}$",
        error_messages={
            "invalid": "کد باید ۶ رقم باشد."
        }
    )

    def validate_phone(self, value):

        try:
            return normalize_phone(value)

        except ValueError:
            raise serializers.ValidationError(
                "شماره موبایل معتبر نیست."
            )

class PasswordResetVerifyOTPResponseSerializer(serializers.Serializer):

    detail = serializers.CharField()

    reset_token = serializers.CharField()

    expires_in = serializers.IntegerField()

class PasswordResetConfirmSerializer(serializers.Serializer):

    reset_token = serializers.CharField(
        write_only=True
    )

    new_password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        style={"input_type": "password"}
    )

    confirm_password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        style={"input_type": "password"}
    )

    def validate(self, attrs):

        if attrs["new_password"] != attrs["confirm_password"]:

            raise serializers.ValidationError({
                "confirm_password": "تکرار رمز عبور با رمز جدید مطابقت ندارد."
            })

        return attrs

class PasswordResetConfirmResponseSerializer(serializers.Serializer):

    detail = serializers.CharField()