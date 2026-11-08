from django.shortcuts import render

# Create your views here.
import secrets
import logging

from datetime import timedelta

from django.conf import settings

from django.contrib.auth.hashers import (
    make_password,
    check_password
)

from django.db import transaction, IntegrityError

from django.utils import timezone

from rest_framework.views import APIView

from rest_framework.response import Response

from rest_framework import status

from rest_framework.permissions import AllowAny

from rest_framework.throttling import AnonRateThrottle

from rest_framework_simplejwt.tokens import RefreshToken

from .models import User, OTPChallenge

from drf_spectacular.utils import (
    extend_schema,
    OpenApiResponse,
)

from .serializers import (
    RegisterSendOTPSerializer,
    RegisterVerifyOTPSerializer,
    OTPSendResponseSerializer,
    RegisterSuccessResponseSerializer,
)

from .services import (
    send_otp_sms,
    OTPProviderError
)


logger = logging.getLogger(__name__)


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

        400: OpenApiResponse(
            description="Invalid phone number."
        ),

        409: OpenApiResponse(
            description="Phone number already registered."
        ),

        429: OpenApiResponse(
            description="OTP resend cooldown."
        ),

        502: OpenApiResponse(
            description="SMS provider error."
        ),
    },
)
    def post(self, request):

        serializer = RegisterSendOTPSerializer(
            data=request.data
        )

        serializer.is_valid(raise_exception=True)

        phone = serializer.validated_data["phone"]

        now = timezone.now()

        # Check existing account

        if User.objects.filter(phone=phone).exists():

            return Response(
                {
                    "detail": "این شماره قبلاً ثبت‌نام کرده است."
                },
                status=status.HTTP_409_CONFLICT
            )

        # Resend cooldown

        recent_challenge = OTPChallenge.objects.filter(
            phone=phone,
            purpose=OTPChallenge.Purpose.REGISTER,
            created_at__gte=now - timedelta(
                seconds=settings.OTP_RESEND_COOLDOWN_SECONDS
            )
        ).order_by("-created_at").first()

        if recent_challenge:

            return Response(
                {
                    "detail": "لطفاً برای ارسال مجدد کد کمی صبر کنید."
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        # Invalidate previous codes

        OTPChallenge.objects.filter(
            phone=phone,
            purpose=OTPChallenge.Purpose.REGISTER,
            consumed_at__isnull=True,
            expires_at__gt=now
        ).update(
            expires_at=now
        )

        # Generate 6 digit OTP

        code = f"{secrets.randbelow(1000000):06d}"

        # Save hashed OTP

        challenge = OTPChallenge.objects.create(

            phone=phone,

            purpose=OTPChallenge.Purpose.REGISTER,

            code_hash=make_password(code),

            expires_at=now + timedelta(
                seconds=settings.OTP_TTL_SECONDS
            ),

        )

        # Send SMS

        try:

            send_otp_sms(
                phone,
                code
            )

        except OTPProviderError:

            challenge.expires_at = timezone.now()

            challenge.save(
                update_fields=["expires_at"]
            )

            logger.exception(
                "OTP provider failed. Challenge ID: %s",
                challenge.id
            )

            return Response(
                {
                    "detail": "ارسال پیامک با مشکل مواجه شد."
                },
                status=status.HTTP_502_BAD_GATEWAY
            )

        return Response(
            {
                "detail": "کد تأیید ارسال شد.",
                "expires_in": settings.OTP_TTL_SECONDS,
                "resend_after": settings.OTP_RESEND_COOLDOWN_SECONDS
            },
            status=status.HTTP_200_OK
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
            400: OpenApiResponse(
                description="Invalid or expired OTP."
            ),
            409: OpenApiResponse(
                description="Phone number or username already exists."
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
        user = None

        try:

            with transaction.atomic():

                # Lock the latest unused challenge.
                # Expiration is checked AFTER acquiring the lock.

                challenge = (
                    OTPChallenge.objects
                    .select_for_update()
                    .filter(
                        phone=data["phone"],
                        purpose=OTPChallenge.Purpose.REGISTER,
                        consumed_at__isnull=True,
                    )
                    .order_by("-created_at")
                    .first()
                )

                # Get fresh time after acquiring the lock.
                now = timezone.now()

                if challenge is None:

                    error = (
                        "کد تأیید معتبر نیست یا قبلاً استفاده شده است."
                    )

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

                    # Count this verification attempt.
                    challenge.attempt_count += 1

                    # Verify OTP hash.
                    if not check_password(
                        data["code"],
                        challenge.code_hash
                    ):

                        update_fields = ["attempt_count"]

                        if (
                            challenge.attempt_count
                            >= settings.OTP_MAX_ATTEMPTS
                        ):

                            challenge.expires_at = now
                            update_fields.append("expires_at")

                            error = (
                                "تعداد تلاش‌های مجاز تمام شده است."
                            )

                        else:

                            error = "کد واردشده صحیح نیست."

                        challenge.save(
                            update_fields=update_fields
                        )

                    # Prevent duplicate registration.
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

                        # Create user inside the same transaction.
                        # Create user only after successful OTP

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

                        # Connect OTP to user

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

                        # Consume OTP and connect it to the user.
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

            logger.warning(
                "Signup integrity conflict.",
                exc_info=True
            )

            return Response(
                {
                    "detail": (
                        "شماره موبایل یا نام کاربری قبلاً ثبت شده است."
                    )
                },
                status=status.HTTP_409_CONFLICT
            )

        if error:

            return Response(
                {
                    "detail": error
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        if user is None:

            logger.error(
                "Signup completed without a user object."
            )

            return Response(
                {
                    "detail": "خطای داخلی هنگام ثبت‌نام."
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # Generate JWT only after successful database transaction.
        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "detail": "ثبت‌نام با موفقیت انجام شد.",

                "user": {
                    "id": user.id,
                    "phone": user.phone,
                    "username": user.username,
                    "full_name": user.full_name,
                },

                "access": str(refresh.access_token),

                "refresh": str(refresh),
            },
            status=status.HTTP_201_CREATED
        )