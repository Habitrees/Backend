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
    RegisterVerifyOTPResponseSerializer,
    RegisterCompleteSerializer,
)
from .services import OTPProviderError, send_otp_sms
from .throttles import LoginRateThrottle

from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect

from rest_framework_simplejwt.exceptions import TokenError


logger = logging.getLogger(__name__)

PASSWORD_RESET_SIGNING_SALT = "habitree.password-reset"
PASSWORD_RESET_TOKEN_TTL_SECONDS = getattr(
    settings,
    "PASSWORD_RESET_TOKEN_TTL_SECONDS",
    300,
)
REGISTRATION_SIGNING_SALT = "habitree.registration"

REGISTRATION_TOKEN_TTL_SECONDS = int(
    getattr(settings, "REGISTRATION_TOKEN_TTL_SECONDS", 600)
)


def set_refresh_cookie(response, refresh, remember_me=True):

    max_age = (
        settings.AUTH_REFRESH_COOKIE_MAX_AGE
        if remember_me
        else None
    )

    response.set_cookie(
        key=settings.AUTH_REFRESH_COOKIE_NAME,
        value=str(refresh),
        max_age=max_age,
        httponly=settings.AUTH_REFRESH_COOKIE_HTTPONLY,
        secure=settings.AUTH_REFRESH_COOKIE_SECURE,
        samesite=settings.AUTH_REFRESH_COOKIE_SAMESITE,
        path=settings.AUTH_REFRESH_COOKIE_PATH,
        domain=settings.AUTH_REFRESH_COOKIE_DOMAIN,
    )

    return response


def clear_refresh_cookie(response):

    response.delete_cookie(
        key=settings.AUTH_REFRESH_COOKIE_NAME,
        path=settings.AUTH_REFRESH_COOKIE_PATH,
        domain=settings.AUTH_REFRESH_COOKIE_DOMAIN,
        samesite=settings.AUTH_REFRESH_COOKIE_SAMESITE,
    )

    return response


class CsrfTokenView(APIView):

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):

        return Response(
            {
                "csrfToken": get_token(request._request)
            },
            status=status.HTTP_200_OK,
        )


@method_decorator(csrf_protect, name="dispatch")
class CookieTokenRefreshView(APIView):

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AnonRateThrottle]

    def post(self, request):

        raw_refresh = request.COOKIES.get(
            settings.AUTH_REFRESH_COOKIE_NAME
        )

        if not raw_refresh:

            response = Response(
                {"detail": "نشست کاربری معتبر نیست."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

            return clear_refresh_cookie(response)

        try:

            refresh = RefreshToken(raw_refresh)

            user_id = refresh.get("user_id")

            user = User.objects.filter(
                pk=user_id,
                is_active=True,
            ).first()

            if user is None:
                raise TokenError("User is inactive or missing.")

            access_token = str(refresh.access_token)

        except (
            TokenError,
            KeyError,
            TypeError,
            ValueError,
        ):

            response = Response(
                {
                    "detail": (
                        "نشست شما منقضی شده است. "
                        "لطفاً مجدداً وارد شوید."
                    )
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

            return clear_refresh_cookie(response)

        return Response(
            {
                "access": access_token,
                "detail": "توکن دسترسی با موفقیت تمدید شد.",
            },
            status=status.HTTP_200_OK,
        )



@method_decorator(csrf_protect, name="dispatch")
class CookieTokenBlacklistView(APIView):

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):

        raw_refresh = request.COOKIES.get(
            settings.AUTH_REFRESH_COOKIE_NAME
        )

        if raw_refresh:

            try:

                refresh = RefreshToken(raw_refresh)
                refresh.blacklist()

            except TokenError:
                pass

        response = Response(
            {
                "detail": "با موفقیت از حساب خارج شدید."
            },
            status=status.HTTP_200_OK,
        )

        return clear_refresh_cookie(response)





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
        summary="Verify Registration OTP",
        description=(
            "Verify the registration OTP without creating a user. "
            "Returns a short-lived registration token."
        ),
        request=RegisterVerifyOTPSerializer,
        responses={
            200: RegisterVerifyOTPResponseSerializer,
            400: OpenApiResponse(
                description="Invalid or expired OTP."
            ),
            409: OpenApiResponse(
                description="Phone number already registered."
            ),
        },
    )
    def post(self, request):

        serializer = RegisterVerifyOTPSerializer(
            data=request.data
        )

        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        error = None
        registration_token = None

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

                    error = (
                        "کد تأیید معتبر نیست یا قبلاً استفاده شده است."
                    )

                elif challenge.verified_at is not None:

                    error = "این کد قبلاً تأیید شده است."

                elif challenge.attempt_count >= settings.OTP_MAX_ATTEMPTS:

                    if challenge.expires_at > now:

                        challenge.expires_at = now

                        challenge.save(
                            update_fields=["expires_at"]
                        )

                    error = "تعداد تلاش‌های مجاز تمام شده است."

                elif challenge.expires_at <= now:

                    error = "کد تأیید منقضی شده است."

                else:

                    challenge.attempt_count += 1

                    if not check_password(
                        data["code"],
                        challenge.code_hash
                    ):

                        fields = ["attempt_count"]

                        if challenge.attempt_count >= settings.OTP_MAX_ATTEMPTS:

                            challenge.expires_at = now

                            fields.append("expires_at")

                            error = "تعداد تلاش‌های مجاز تمام شده است."

                        else:

                            error = "کد واردشده صحیح نیست."

                        challenge.save(
                            update_fields=fields
                        )

                    elif User.objects.filter(
                        phone=data["phone"]
                    ).exists():

                        challenge.expires_at = now

                        challenge.save(
                            update_fields=[
                                "attempt_count",
                                "expires_at",
                            ]
                        )

                        error = "این شماره قبلاً ثبت شده است."

                    else:

                        challenge.verified_at = now

                        challenge.expires_at = (
                            now + timedelta(
                                seconds=REGISTRATION_TOKEN_TTL_SECONDS
                            )
                        )

                        challenge.save(
                            update_fields=[
                                "attempt_count",
                                "verified_at",
                                "expires_at",
                            ]
                        )

                        registration_token = signing.dumps(
                            {
                                "challenge_id": str(challenge.pk),
                                "phone": challenge.phone,
                            },
                            salt=REGISTRATION_SIGNING_SALT,
                            compress=True,
                        )

        except IntegrityError:

            logger.exception(
                "Registration OTP verification integrity error."
            )

            return Response(
                {"detail": "خطا در تأیید شماره موبایل."},
                status=status.HTTP_409_CONFLICT,
            )

        if error:

            return Response(
                {"detail": error},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "detail": "شماره موبایل با موفقیت تأیید شد.",
                "registration_token": registration_token,
                "expires_in": REGISTRATION_TOKEN_TTL_SECONDS,
            },
            status=status.HTTP_200_OK,
        )



@method_decorator(csrf_protect, name="dispatch")
class RegisterCompleteView(APIView):

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AnonRateThrottle]

    @extend_schema(
        tags=["Authentication"],
        summary="Complete Registration",
        description=(
            "Create a new account using a valid registration token "
            "issued after successful OTP verification."
        ),
        request=RegisterCompleteSerializer,
        responses={
            201: RegisterSuccessResponseSerializer,
            400: OpenApiResponse(
                description="Invalid registration token or password."
            ),
            409: OpenApiResponse(
                description="Phone number or username already exists."
            ),
        },
    )
    def post(self, request):

        serializer = RegisterCompleteSerializer(
            data=request.data
        )

        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        # -----------------------------------------
        # 1. Validate registration token
        # -----------------------------------------

        try:

            payload = signing.loads(
                data["registration_token"],
                salt=REGISTRATION_SIGNING_SALT,
                max_age=REGISTRATION_TOKEN_TTL_SECONDS,
            )

            if not isinstance(payload, dict):
                raise ValueError("Invalid token payload.")

            challenge_id = payload["challenge_id"]
            phone = payload["phone"]

            if not isinstance(phone, str):
                raise ValueError("Invalid phone.")

        except (
            signing.BadSignature,
            KeyError,
            TypeError,
            ValueError,
        ):

            return Response(
                {
                    "detail": (
                        "توکن ثبت‌نام نامعتبر است یا منقضی شده است."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        error = None
        conflict = False
        password_errors = None
        user = None

        # -----------------------------------------
        # 2. Lock challenge and create user
        # -----------------------------------------

        try:

            with transaction.atomic():

                challenge = (
                    OTPChallenge.objects.select_for_update()
                    .filter(
                        pk=challenge_id,
                        phone=phone,
                        purpose=OTPChallenge.Purpose.REGISTER,
                        verified_at__isnull=False,
                        consumed_at__isnull=True,
                    )
                    .first()
                )

                now = timezone.now()

                if challenge is None:

                    error = (
                        "درخواست ثبت‌نام معتبر نیست "
                        "یا قبلاً استفاده شده است."
                    )

                elif challenge.expires_at <= now:

                    error = "مهلت تکمیل ثبت‌نام به پایان رسیده است."

                elif User.objects.filter(
                    phone=challenge.phone
                ).exists():

                    conflict = True

                else:

                    # Validate password against user attributes.
                    candidate_user = User(
                        phone=challenge.phone,
                        username=data["username"],
                        full_name=data["full_name"],
                    )

                    try:

                        validate_password(
                            data["password"],
                            user=candidate_user,
                        )

                    except DjangoValidationError as exc:

                        password_errors = exc.messages

                    else:

                        # Create user only after OTP verification.
                        user = User.objects.create_user(
                            phone=challenge.phone,
                            username=data["username"],
                            full_name=data["full_name"],
                            password=data["password"],
                            phone_verified_at=challenge.verified_at,
                            timezone=data["timezone"],
                            locale=data["locale"],
                            terms_version=settings.TERMS_VERSION,
                            terms_accepted_at=now,
                            is_active=True,
                        )

                        # Bind and consume OTP challenge.
                        challenge.user = user
                        challenge.consumed_at = now

                        challenge.save(
                            update_fields=[
                                "user",
                                "consumed_at",
                            ]
                        )

        except IntegrityError:

            logger.exception(
                "Registration completion integrity conflict."
            )

            return Response(
                {
                    "detail": (
                        "شماره موبایل یا نام کاربری قبلاً ثبت شده است."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )

        # -----------------------------------------
        # 3. Handle validation errors
        # -----------------------------------------

        if conflict:

            return Response(
                {
                    "detail": (
                        "این شماره موبایل قبلاً ثبت شده است."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )

        if error:

            return Response(
                {"detail": error},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if password_errors:

            return Response(
                {"password": password_errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if user is None:

            logger.error(
                "Registration completion failed without user."
            )

            return Response(
                {"detail": "خطای داخلی هنگام ثبت‌نام."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # -----------------------------------------
        # 4. Issue JWT tokens
        # -----------------------------------------

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


@method_decorator(csrf_protect, name="dispatch")
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

        remember_me = serializer.validated_data["remember_me"]

        refresh = RefreshToken.for_user(user)

        refresh_lifetime = (
            settings.AUTH_REFRESH_REMEMBER_ME_LIFETIME
            if remember_me
            else settings.AUTH_REFRESH_SESSION_LIFETIME
        )

        refresh.set_exp(
            lifetime=refresh_lifetime
        )

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

        return set_refresh_cookie(
            response,
            refresh,
            remember_me=remember_me
        )


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
