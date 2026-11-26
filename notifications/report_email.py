import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from drf_spectacular.utils import extend_schema

from rest_framework import serializers
from rest_framework.exceptions import (
    APIException,
    ValidationError,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import ReportEmail


SALT = "habitree-report-email"


class MailUnavailable(APIException):

    status_code = 503

    default_detail = (
        "Email verification service is unavailable."
    )


class EmailInput(serializers.Serializer):

    email = serializers.EmailField()


class VerificationInput(serializers.Serializer):

    token = serializers.CharField(
        max_length=2048
    )


class ReportEmailSerializer(
    serializers.ModelSerializer
):

    class Meta:
        model = ReportEmail

        fields = (
            "email",
            "verified_at",
        )

        read_only_fields = fields


@extend_schema(tags=["Notifications"])
class ReportEmailView(APIView):

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses=ReportEmailSerializer
    )
    def get(self, request):

        destination = ReportEmail.objects.filter(
            user=request.user
        ).first()

        if destination is None:

            return Response({
                "email": None,
                "verified_at": None,
            })

        return Response(
            ReportEmailSerializer(
                destination
            ).data
        )

    @extend_schema(
        responses={204: None}
    )
    def delete(self, request):

        ReportEmail.objects.filter(
            user=request.user
        ).delete()

        return Response(status=204)


@extend_schema(tags=["Notifications"])
class RequestReportEmailView(APIView):

    permission_classes = [IsAuthenticated]

    throttle_classes = [ScopedRateThrottle]

    throttle_scope = "report_email"

    @extend_schema(
        request=EmailInput,
        responses={202: dict},
    )
    def post(self, request):

        if not settings.REPORT_EMAIL_VERIFICATION_ENABLED:

            raise MailUnavailable()

        serializer = EmailInput(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        with transaction.atomic():

            user = get_user_model().objects.select_for_update().get(
                pk=request.user.pk
            )

            destination, _ = (
                ReportEmail.objects.update_or_create(
                    user=user,
                    defaults={
                        "email":
                            serializer.validated_data["email"],
                        "verification_nonce":
                            uuid.uuid4(),
                        "verified_at":
                            None,
                    },
                )
            )

            token = signing.dumps(
                {
                    "user_id": user.pk,
                    "nonce": str(
                        destination.verification_nonce
                    ),
                },
                salt=SALT,
            )

        try:

            delivered = send_mail(
                subject="Habitree Email Verification",
                message=(
                    "Enter this verification token "
                    "in Habitree:\n\n"
                    + token
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[
                    destination.email
                ],
                fail_silently=False,
            )

        except Exception:

            raise MailUnavailable()

        if delivered != 1:

            raise MailUnavailable()

        return Response(
            {"detail": "Verification email submitted."},
            status=202,
        )


@extend_schema(tags=["Notifications"])
class ConfirmReportEmailView(APIView):

    permission_classes = [IsAuthenticated]

    throttle_classes = [ScopedRateThrottle]

    throttle_scope = "report_email_confirm"

    @extend_schema(
        request=VerificationInput,
        responses=ReportEmailSerializer,
    )
    @transaction.atomic
    def post(self, request):

        serializer = VerificationInput(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        try:

            data = signing.loads(
                serializer.validated_data["token"],
                salt=SALT,
                max_age=600,
            )

        except signing.BadSignature:

            raise ValidationError({
                "token": "Invalid or expired token."
            })

        if data.get("user_id") != request.user.pk:

            raise ValidationError({
                "token": "Invalid verification token."
            })

        destination = (
            ReportEmail.objects.select_for_update()
            .filter(user=request.user)
            .first()
        )

        if (
            destination is None
            or str(destination.verification_nonce)
                != data.get("nonce")
        ):

            raise ValidationError({
                "token": "Invalid verification token."
            })

        destination.verified_at = timezone.now()

        destination.verification_nonce = uuid.uuid4()

        destination.save(
            update_fields=[
                "verified_at",
                "verification_nonce",
                "updated_at",
            ]
        )

        return Response(
            ReportEmailSerializer(
                destination
            ).data
        )