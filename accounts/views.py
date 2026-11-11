import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.password_validation import validate_password
from django.core import signing
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)

from drf_spectacular.utils import extend_schema, OpenApiResponse

from .models import OTPChallenge, User
from .serializers import (
    LoginSerializer,
    LoginSuccessResponseSerializer,
    OTPSendResponseSerializer,
    PasswordResetConfirmResponseSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetSendOTPSerializer,
    PasswordResetVerifyOTPResponseSerializer,
    PasswordResetVerifyOTPSerializer,
    RegisterSendOTPSerializer,
    RegisterSuccessResponseSerializer,
    RegisterVerifyOTPSerializer,
)
from .services import OTPProviderError, send_otp_sms
from .throttles import LoginRateThrottle


logger = logging.getLogger(__name__)

PASSWORD_RESET_SIGNING_SALT = "habitree.password-reset"
PASSWORD_RESET_TOKEN_TTL_SECONDS = getattr(
    settings,
    "PASSWORD_RESET_TOKEN_TTL_SECONDS",
    300,
)


def set_refresh_cookie(response, refresh):
    response.set_cookie(
        key=settings.AUTH_REFRESH_COOKIE_NAME,
        value=str(refresh),
        max_age=settings.AUTH_REFRESH_COOKIE_MAX_AGE,
        httponly=settings.AUTH_REFRESH_COOKIE_HTTPONLY,
        secure=settings.AUTH_REFRESH_COOKIE_SECURE,
        samesite=settings.AUTH_REFRESH_COOKIE_SAMESITE,
        path=settings.AUTH_REFRESH_COOKIE_PATH,
        domain=settings.AUTH_REFRESH_COOKIE_DOMAIN,
    )
    return response


class RegisterSendOTPView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    @extend_schema(
        tags=["Authentication"],
        summary="Send Registration OTP",
        description="Send a six-digit verification code to user's mobile number.",
        request=RegisterSendOTPSerializer,
        responses={
            200: OTPSendResponseSerializer,
            400: OpenApiResponse(description="Invalid phone number."),
            409: OpenApiResponse(description="Phone number already registered."),
            429: OpenApiResponse(description="OTP resend cooldown."),
            502: OpenApiResponse(description="SMS provider error."),
        },
    )
    def post(self, request):
        serializer = RegisterSendOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        phone = serializer.validated_data["phone"]
        now = timezone.now()

        if User.objects.filter(phone=phone).exists():
            return Response(
                {"detail": "این شماره قبلاً ثبت‌نام کرده است."},
                status=status.HTTP_409_CONFLICT,
            )

        recent_challenge = (
            OTPChallenge.objects.filter(
                phone=phone,
                purpose=OTPChallenge.Purpose.REGISTER,
                created_at__gte=now - timedelta(
                    seconds=settings.OTP_RESEND_COOLDOWN_SECONDS
                ),
            )
            .order_by("-created_at")
            .first()
        )

        if recent_challenge:
            return Response(
                {"detail": "لطفاً برای ارسال مجدد کد کمی صبر کنید."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        OTPChallenge.objects.filter(
            phone=phone,
            purpose=OTPChallenge.Purpose.REGISTER,
            consumed_at__isnull=True,
            expires_at__gt=now,
        ).update(expires_at=now)

        code = f"{secrets.randbelow(1_000_000):06d}"

        challenge = OTPChallenge.objects.create(
            phone=phone,
            purpose=OTPChallenge.Purpose.REGISTER,
            code_hash=make_password(code),
            expires_at=now + timedelta(seconds=settings.OTP_TTL_SECONDS),
        )

        try:
            send_otp_sms(phone, code)
        except OTPProviderError:
            OTPChallenge.objects.filter(pk=challenge.pk).update(
                expires_at=timezone.now()
            )
            logger.exception(
                "Registration OTP provider failed. Challenge ID: %s",
                challenge.id,
            )
            return Response(
                {"detail": "ارسال پیامک با مشکل مواجه شد."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(
            {
                "detail": "کد تأیید ارسال شد.",
                "expires_in": settings.OTP_TTL_SECONDS,
                "resend_after": settings.OTP_RESEND_COOLDOWN_SECONDS,
            },
            status=status.HTTP_200_OK,
        )


class RegisterVerifyOTPView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    @extend_schema(
        tags=["Authentication"],
        summary="Verify OTP and Register User",
        description="Verify OTP and create a new Habitree account.",
        request=RegisterVerifyOTPSerializer,
        responses={
            201: RegisterSuccessResponseSerializer,
            400: OpenApiResponse(description="Invalid or expired OTP."),
            409: OpenApiResponse(
                description="Phone number or username already exists."
            ),
        },
    )
    def post(self, request):
        serializer = RegisterVerifyOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        error = None
        user = None

        try:
            with transaction.atomic():
                challenge = (
                    OTPChallenge.objects.select_for_update()
                    .filter(
                        phone=data["phone"],
                        purpose=OTPChallenge.Purpose.REGISTER,
                        consumed_at__isnull=True,
                    )
                    .order_by("-created_at")
                    .first()
                )

                now = timezone.now()

                if challenge is None:
                    error = "کد تأیید معتبر نیست یا قبلاً استفاده شده است."

                elif challenge.attempt_count >= settings.OTP_MAX_ATTEMPTS:
                    if challenge.expires_at > now:
                        challenge.expires_at = now
                        challenge.save(update_fields=["expires_at"])
                    error = "تعداد تلاش‌های مجاز تمام شده است."

                elif challenge.expires_at <= now:
                    error = "کد تأیید منقضی شده است."

                else:
                    challenge.attempt_count += 1

                    if not check_password(data["code"], challenge.code_hash):
                        update_fields = ["attempt_count"]

                        if challenge.attempt_count >= settings.OTP_MAX_ATTEMPTS:
                            challenge.expires_at = now
                            update_fields.append("expires_at")
                            error = "تعداد تلاش‌های مجاز تمام شده است."
                        else:
                            error = "کد واردشده صحیح نیست."

                        challenge.save(update_fields=update_fields)

                    elif User.objects.filter(phone=data["phone"]).exists():
                        challenge.expires_at = now
                        challenge.save(
                            update_fields=["attempt_count", "expires_at"]
                        )
                        error = "این شماره قبلاً ثبت شده است."

                    else:
                        user = User.objects.create_user(
                            phone=data["phone"],
                            username=data["username"],
                            full_name=data["full_name"],
                            password=data["password"],
                            phone_verified_at=now,
                            timezone=data["timezone"],
                            locale=data["locale"],
                            terms_version=settings.TERMS_VERSION,
                            terms_accepted_at=now,
                            is_active=True,
                        )

                        challenge.user = user
                        challenge.verified_at = now
                        challenge.consumed_at = now
                        challenge.save(
                            update_fields=[
                                "attempt_count",
                                "user",
                                "verified_at",
                                "consumed_at",
                            ]
                        )

        except IntegrityError:
            logger.warning("Signup integrity conflict.", exc_info=True)
            return Response(
                {
                    "detail": (
                        "شماره موبایل یا نام کاربری قبلاً ثبت شده است."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )

        if error:
            return Response(
                {"detail": error},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if user is None:
            logger.error("Signup completed without a user object.")
            return Response(
                {"detail": "خطای داخلی هنگام ثبت‌نام."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        refresh = RefreshToken.for_user(user)

        response = Response(
            {
                "detail": "ثبت‌نام با موفقیت انجام شد.",
                "user": {
                    "id": user.id,
                    "phone": user.phone,
                    "username": user.username,
                    "full_name": user.full_name,
                },
                "access": str(refresh.access_token),
            },
            status=status.HTTP_201_CREATED,
        )

        return set_refresh_cookie(response, refresh)


class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]

    @extend_schema(
        tags=["Authentication"],
        summary="User Login",
        description=(
            "Authenticate user using phone number and password, "
            "then return JWT tokens."
        ),
        request=LoginSerializer,
        responses={
            200: LoginSuccessResponseSerializer,
            400: OpenApiResponse(description="Invalid credentials."),
            429: OpenApiResponse(description="Too many login attempts."),
        },
    )
    def post(self, request):
        serializer = LoginSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data["user"]

        refresh = RefreshToken.for_user(user)

        response = Response(
            {
                "detail": "ورود با موفقیت انجام شد.",
                "user": {
                    "id": user.id,
                    "phone": user.phone,
                    "username": user.username,
                    "full_name": user.full_name,
                },
                "access": str(refresh.access_token),
            },
            status=status.HTTP_200_OK,
        )

        return set_refresh_cookie(response, refresh)


class PasswordResetSendOTPView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    # Reuse the existing 5/minute anonymous login throttle.
    # This avoids depending on a throttle class not present in the
    # currently supplied accounts/throttles.py.
    throttle_classes = [LoginRateThrottle]

    @extend_schema(
        tags=["Authentication"],
        summary="Send Password Reset OTP",
        description=(
            "Request a password reset OTP. A generic response is returned "
            "regardless of account eligibility."
        ),
        request=PasswordResetSendOTPSerializer,
        responses={
            200: OTPSendResponseSerializer,
            400: OpenApiResponse(description="Invalid phone number."),
            429: OpenApiResponse(description="Too many requests."),
        },
    )
    def post(self, request):
        serializer = PasswordResetSendOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        phone = serializer.validated_data["phone"]
        response_data = {
            "detail": (
                "در صورت وجود حساب فعال با شماره تأییدشده، "
                "کد بازیابی ارسال خواهد شد."
            ),
            "expires_in": settings.OTP_TTL_SECONDS,
            "resend_after": settings.OTP_RESEND_COOLDOWN_SECONDS,
        }

        challenge = None
        code = None

        with transaction.atomic():
            user = (
                User.objects.select_for_update()
                .filter(
                    phone=phone,
                    is_active=True,
                    phone_verified_at__isnull=False,
                )
                .first()
            )

            # Keep the response identical to prevent account enumeration.
            if user is None:
                return Response(response_data, status=status.HTTP_200_OK)

            now = timezone.now()

            recent_challenge = (
                OTPChallenge.objects.filter(
                    user=user,
                    purpose=OTPChallenge.Purpose.PASSWORD_RESET,
                    consumed_at__isnull=True,
                    expires_at__gt=now,
                    created_at__gte=now - timedelta(
                        seconds=settings.OTP_RESEND_COOLDOWN_SECONDS
                    ),
                )
                .order_by("-created_at")
                .first()
            )

            if recent_challenge:
                return Response(response_data, status=status.HTTP_200_OK)

            # Expire older reset challenges, including previously verified
            # challenges, so their signed reset tokens cannot be used.
            OTPChallenge.objects.filter(
                user=user,
                purpose=OTPChallenge.Purpose.PASSWORD_RESET,
                consumed_at__isnull=True,
                expires_at__gt=now,
            ).update(expires_at=now)

            code = f"{secrets.randbelow(1_000_000):06d}"

            challenge = OTPChallenge.objects.create(
                user=user,
                phone=phone,
                purpose=OTPChallenge.Purpose.PASSWORD_RESET,
                code_hash=make_password(code),
                expires_at=now + timedelta(seconds=settings.OTP_TTL_SECONDS),
            )

        try:
            send_otp_sms(phone, code)
        except OTPProviderError:
            OTPChallenge.objects.filter(
                pk=challenge.pk,
                consumed_at__isnull=True,
            ).update(expires_at=timezone.now())

            logger.exception(
                "Password reset OTP provider failed. Challenge ID: %s",
                challenge.id,
            )
            # Deliberately keep the public response generic.

        return Response(response_data, status=status.HTTP_200_OK)


class PasswordResetVerifyOTPView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [LoginRateThrottle]

    @extend_schema(
        tags=["Authentication"],
        summary="Verify Password Reset OTP",
        description=(
            "Verify the password reset OTP and issue a short-lived "
            "password-reset token."
        ),
        request=PasswordResetVerifyOTPSerializer,
        responses={
            200: PasswordResetVerifyOTPResponseSerializer,
            400: OpenApiResponse(
                description="Invalid, expired or already used OTP."
            ),
            429: OpenApiResponse(description="Too many verification attempts."),
        },
    )
    def post(self, request):
        serializer = PasswordResetVerifyOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        phone = serializer.validated_data["phone"]
        code = serializer.validated_data["code"]

        error = None
        reset_token = None

        # Lock order is User -> OTPChallenge, matching the send endpoint.
        # This avoids opposite lock ordering between concurrent reset calls.
        with transaction.atomic():
            user = (
                User.objects.select_for_update()
                .filter(
                    phone=phone,
                    is_active=True,
                    phone_verified_at__isnull=False,
                )
                .first()
            )

            if user is None:
                error = "کد تأیید معتبر نیست یا منقضی شده است."
            else:
                challenge = (
                    OTPChallenge.objects.select_for_update()
                    .filter(
                        user=user,
                        phone=phone,
                        purpose=OTPChallenge.Purpose.PASSWORD_RESET,
                        consumed_at__isnull=True,
                    )
                    .order_by("-created_at")
                    .first()
                )

                now = timezone.now()

                if challenge is None:
                    error = "کد تأیید معتبر نیست یا منقضی شده است."

                elif challenge.attempt_count >= settings.OTP_MAX_ATTEMPTS:
                    if challenge.expires_at > now:
                        challenge.expires_at = now
                        challenge.save(update_fields=["expires_at"])
                    error = "تعداد تلاش‌های مجاز تمام شده است."

                elif challenge.verified_at is not None:
                    error = "این کد قبلاً تأیید شده است."

                elif challenge.expires_at <= now:
                    error = "کد تأیید منقضی شده است."

                else:
                    challenge.attempt_count += 1

                    if not check_password(code, challenge.code_hash):
                        update_fields = ["attempt_count"]

                        if challenge.attempt_count >= settings.OTP_MAX_ATTEMPTS:
                            challenge.expires_at = now
                            update_fields.append("expires_at")
                            error = "تعداد تلاش‌های مجاز تمام شده است."
                        else:
                            error = "کد واردشده صحیح نیست."

                        challenge.save(update_fields=update_fields)

                    else:
                        challenge.verified_at = now
                        challenge.expires_at = now + timedelta(
                            seconds=PASSWORD_RESET_TOKEN_TTL_SECONDS
                        )
                        challenge.save(
                            update_fields=[
                                "attempt_count",
                                "verified_at",
                                "expires_at",
                            ]
                        )

                        reset_token = signing.dumps(
                            {
                                "challenge_id": str(challenge.pk),
                                "user_id": user.pk,
                            },
                            salt=PASSWORD_RESET_SIGNING_SALT,
                            compress=True,
                        )

        if error:
            return Response(
                {"detail": error},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if reset_token is None:
            logger.error("Password reset OTP verified without a reset token.")
            return Response(
                {"detail": "خطای داخلی هنگام تأیید کد."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                "detail": "کد تأیید با موفقیت تأیید شد.",
                "reset_token": reset_token,
                "expires_in": PASSWORD_RESET_TOKEN_TTL_SECONDS,
            },
            status=status.HTTP_200_OK,
        )


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [LoginRateThrottle]

    @extend_schema(
        tags=["Authentication"],
        summary="Confirm Password Reset",
        description=(
            "Set a new password using a valid, short-lived "
            "password-reset token."
        ),
        request=PasswordResetConfirmSerializer,
        responses={
            200: PasswordResetConfirmResponseSerializer,
            400: OpenApiResponse(description="Invalid token or password."),
            429: OpenApiResponse(description="Too many requests."),
        },
    )
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        try:
            payload = signing.loads(
                data["reset_token"],
                salt=PASSWORD_RESET_SIGNING_SALT,
                max_age=PASSWORD_RESET_TOKEN_TTL_SECONDS,
            )

            if not isinstance(payload, dict):
                raise ValueError("Invalid reset token payload.")

            challenge_id = payload["challenge_id"]
            user_id = int(payload["user_id"])

        except (
            signing.BadSignature,
            KeyError,
            TypeError,
            ValueError,
        ):
            return Response(
                {
                    "detail": (
                        "توکن تغییر رمز نامعتبر است یا منقضی شده است."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        error = None
        password_errors = None

        # Lock order is User -> OTPChallenge, matching the other reset views.
        with transaction.atomic():
            user = (
                User.objects.select_for_update()
                .filter(
                    pk=user_id,
                    is_active=True,
                    phone_verified_at__isnull=False,
                )
                .first()
            )

            if user is None:
                error = "درخواست تغییر رمز معتبر نیست یا منقضی شده است."
            else:
                now = timezone.now()

                challenge = (
                    OTPChallenge.objects.select_for_update()
                    .filter(
                        pk=challenge_id,
                        user=user,
                        phone=user.phone,
                        purpose=OTPChallenge.Purpose.PASSWORD_RESET,
                        verified_at__isnull=False,
                        consumed_at__isnull=True,
                        expires_at__gt=now,
                    )
                    .first()
                )

                if challenge is None:
                    error = (
                        "درخواست تغییر رمز معتبر نیست یا قبلاً استفاده شده است."
                    )
                else:
                    try:
                        validate_password(data["new_password"], user=user)
                    except DjangoValidationError as exc:
                        password_errors = exc.messages
                    else:
                        user.set_password(data["new_password"])
                        user.save(update_fields=["password"])

                        challenge.consumed_at = now
                        challenge.save(update_fields=["consumed_at"])

                        # Invalidate all other reset challenges for this user.
                        OTPChallenge.objects.filter(
                            user=user,
                            purpose=OTPChallenge.Purpose.PASSWORD_RESET,
                            consumed_at__isnull=True,
                        ).exclude(
                            pk=challenge.pk
                        ).update(
                            expires_at=now
                        )

                        # Revoke all outstanding refresh tokens.
                        for outstanding_token in OutstandingToken.objects.filter(
                            user=user
                        ):
                            BlacklistedToken.objects.get_or_create(
                                token=outstanding_token
                            )

        if error:
            return Response(
                {"detail": error},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if password_errors:
            return Response(
                {"new_password": password_errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "detail": (
                    "رمز عبور با موفقیت تغییر کرد. لطفاً مجدداً وارد شوید."
                )
            },
            status=status.HTTP_200_OK,
        )
