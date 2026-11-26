from datetime import timedelta
from hmac import compare_digest

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.urls import path
from django.utils import timezone
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import APIException, AuthenticationFailed, ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts.models import User
from challenges.models import Challenge
from coach.models import AIMessage, AIProposal
from coach.serializers import CoachResult, MessageSerializer
from reports.models import SmartReport
from reports.serializers import ReportDateQuery, ReportSerializer
from reports.services import PERIODS, bounds, build_report
from .pagination import StandardPagination
from challenges.services import get_streak_data, get_plant_data
from coach.services import validate_proposal
from notifications.models import ReportEmail


class WorkflowConflict(APIException):
    status_code = 409
    default_detail = "A different result has already been recorded."


class WorkflowAuthentication(BaseAuthentication):
    def authenticate(self, request):
        view = request.parser_context["view"]
        expected = getattr(settings, view.secret_setting)
        supplied = request.headers.get("X-Workflow-Token", "")
        if not expected or not compare_digest(expected.encode(), supplied.encode()):
            raise AuthenticationFailed("Invalid workflow credentials.")
        return AnonymousUser(), view.secret_setting


class WorkflowAuthSchema(OpenApiAuthenticationExtension):
    target_class = WorkflowAuthentication
    name = "workflowAuth"

    def get_security_definition(self, auto_schema):
        return {"type": "apiKey", "in": "header", "name": "X-Workflow-Token"}


class WorkflowPermission(BasePermission):
    def has_permission(self, request, view):
        return request.auth == view.secret_setting


class WorkflowView(APIView):
    authentication_classes = [WorkflowAuthentication]
    permission_classes = [WorkflowPermission]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "workflow"
    secret_setting = "N8N_REPORT_TOKEN"


class EligibleUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "timezone", "locale")


def eligible_users():

    return User.objects.filter(
        is_active=True
    ).filter(

        Q(
            notification_preference__smart_reports_enabled=True
        )

        | Q(
            notification_preference__email_reports_enabled=True
        )

        | Q(
            notification_preference__telegram_reports_enabled=True
        )
    )


class ReportUsers(WorkflowView, ListAPIView):
    serializer_class = EligibleUserSerializer
    pagination_class = StandardPagination

    def get_queryset(self):
        return eligible_users().order_by("pk")


class ReportResultInput(serializers.Serializer):
    date = serializers.DateField()
    narrative = serializers.CharField(max_length=12000)


class ReportDeliveryInput(serializers.Serializer):
    status = serializers.ChoiceField(choices=("delivered", "failed"))


class SmartReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = SmartReport
        fields = ("id", "period", "period_start", "narrative", "delivery_status", "created_at")


class ReportContext(WorkflowView):
    @extend_schema(parameters=[ReportDateQuery], responses=ReportSerializer)
    def get(self, request, user_id, period):
        user = get_object_or_404(eligible_users(), pk=user_id)
        if period not in PERIODS:
            raise ValidationError({"period": "Use weekly, monthly, or yearly."})
        query = ReportDateQuery(data=request.query_params)
        query.is_valid(raise_exception=True)
        return Response(ReportSerializer(
            build_report(user, period, query.validated_data.get("date")),
        ).data)

    @extend_schema(request=ReportResultInput, responses={200: SmartReportSerializer, 201: SmartReportSerializer})
    def post(self, request, user_id, period):
        user = get_object_or_404(eligible_users(), pk=user_id)
        if period not in PERIODS:
            raise ValidationError({"period": "Use weekly, monthly, or yearly."})
        submitted = ReportResultInput(data=request.data)
        submitted.is_valid(raise_exception=True)
        day = ReportDateQuery().validate_date(submitted.validated_data["date"])
        start, _ = bounds(period, day)
        narrative = submitted.validated_data["narrative"]
        report, created = SmartReport.objects.get_or_create(
            user=user, period=period, period_start=start, defaults={"narrative": narrative},
        )
        if report.narrative != narrative:
            raise WorkflowConflict()
        return Response(SmartReportSerializer(report).data, status=201 if created else 200)


class ReportDelivery(WorkflowView):
    @extend_schema(request=ReportDeliveryInput, responses={200: SmartReportSerializer, 502: SmartReportSerializer})
    @transaction.atomic
    def patch(self, request, pk):
        report = get_object_or_404(
            SmartReport.objects.select_for_update().filter(user__in=eligible_users()), pk=pk,
        )
        submitted = ReportDeliveryInput(data=request.data)
        submitted.is_valid(raise_exception=True)
        new_status = submitted.validated_data["status"]
        if report.delivery_status == SmartReport.Delivery.DELIVERED and new_status != report.delivery_status:
            raise WorkflowConflict()
        report.delivery_status = new_status
        report.save(update_fields=["delivery_status"])
        return Response(
            SmartReportSerializer(report).data,
            status=502 if new_status == SmartReport.Delivery.FAILED else 200,
        )

class ReportRecipientSerializer(serializers.Serializer):

    report_id = serializers.IntegerField()
    channel = serializers.CharField()
    email = serializers.EmailField()


class ReportRecipient(WorkflowView):

    @extend_schema(
        responses=ReportRecipientSerializer
    )
    def get(self, request, pk):

        report = get_object_or_404(
            SmartReport.objects.select_related(
                "user"
            ),
            pk=pk,
            user__is_active=True,
            user__notification_preference__email_reports_enabled=True,
        )

        destination = get_object_or_404(
            ReportEmail.objects.filter(
                user=report.user,
                verified_at__isnull=False,
            )
        )

        return Response(
            ReportRecipientSerializer({
                "report_id": report.pk,
                "channel": "email",
                "email": destination.email,
            }).data
        )
class CoachWorkflow(WorkflowView):
    secret_setting = "N8N_COACH_TOKEN"


class PendingMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIMessage
        fields = ("id",)


class CoachQueue(CoachWorkflow):
    @extend_schema(responses=PendingMessageSerializer(many=True))
    def get(self, request):
        pending = AIMessage.objects.filter(
            conversation__owner__is_active=True, conversation__owner__ai_coach_enabled=True,
            reply_to__isnull=True, response__isnull=True,
        ).order_by("pk")[:25]
        return Response(PendingMessageSerializer(pending, many=True).data)


class WorkflowChallengeSerializer(serializers.Serializer):

    id = serializers.IntegerField()
    title = serializers.CharField()
    description = serializers.CharField()

    kind = serializers.CharField()
    polarity = serializers.CharField()

    target_value = serializers.IntegerField(
        allow_null=True
    )

    unit = serializers.CharField(
        allow_blank=True
    )

    frequency = serializers.CharField()
    mode = serializers.CharField()

    start_date = serializers.DateField()
    end_date = serializers.DateField()

    current_streak = serializers.IntegerField()
    best_streak = serializers.IntegerField()
    consecutive_failures = serializers.IntegerField()

    progress_percent = serializers.FloatField()
    successful_periods = serializers.IntegerField()
    total_periods = serializers.IntegerField()

    recent_performance = serializers.ListField(
        child=serializers.DictField()
    )

class CoachContextSerializer(serializers.Serializer):

    messages = MessageSerializer(many=True)

    challenges = WorkflowChallengeSerializer(
        many=True
    )


class CoachContext(CoachWorkflow):
    @extend_schema(responses=CoachContextSerializer)
    def get(self, request, pk):
        message = get_object_or_404(
            AIMessage.objects.select_related("conversation").filter(
                reply_to__isnull=True, conversation__owner__is_active=True,
                conversation__owner__ai_coach_enabled=True,
            ), pk=pk,
        )
        history = message.conversation.messages.filter(pk__lte=message.pk).select_related(
            "proposal",
        ).order_by("-pk")[:20]
        challenges = []

        queryset = Challenge.objects.filter(
            owner_id=message.conversation.owner_id,
            archived=False,
        ).order_by("-pk")[:25]

        for challenge in queryset:

            streak = get_streak_data(challenge)

            plant = get_plant_data(challenge)

            recent = challenge.logs.order_by(
                "-period_start"
            ).values(
                "period_start",
                "success",
            )[:14]

            challenges.append({

                "id": challenge.pk,

                "title": challenge.title,
                "description": challenge.description,

                "kind": challenge.kind,
                "polarity": challenge.polarity,
                "target_value": challenge.target_value,
                "unit": challenge.unit,

                "frequency": challenge.frequency,
                "mode": challenge.mode,

                "start_date": challenge.start_date,
                "end_date": challenge.end_date,

                "current_streak":
                    streak["current_streak"],

                "best_streak":
                    streak["best_streak"],

                "consecutive_failures":
                    streak["consecutive_failures"],

                "progress_percent":
                    plant["progress_percent"],

                "successful_periods":
                    plant["successful_periods"],

                "total_periods":
                    plant["total_periods"],

                "recent_performance": [
                    {
                        "date": row["period_start"].isoformat(),
                        "success": row["success"],
                    }
                    for row in recent
                ],
            })
        return Response(CoachContextSerializer({
            "messages": list(reversed(history)), "challenges": list(challenges),
        }).data)

    @extend_schema(
        request=CoachResult,
        responses={
            200: MessageSerializer,
            201: MessageSerializer,
        },
    )
    @transaction.atomic
    def post(self, request, pk):

        submitted = CoachResult(
            data=request.data
        )

        submitted.is_valid(
            raise_exception=True
        )

        data = submitted.validated_data

        message = get_object_or_404(
            AIMessage.objects.select_related(
                "conversation"
            ).filter(
                reply_to__isnull=True
            ),
            pk=pk,
        )

        user = get_object_or_404(
            User.objects.select_for_update().filter(
                is_active=True,
                ai_coach_enabled=True,
            ),
            pk=message.conversation.owner_id,
        )

        reply = AIMessage.objects.filter(
            reply_to=message
        ).select_related(
            "proposal"
        ).first()

        proposed = data.get("proposal")

        if reply is not None:

            existing = getattr(
                reply,
                "proposal",
                None,
            )

            existing_data = None

            if existing:

                existing_data = {
                    "action": existing.action,
                    "changes": existing.changes,
                }

                if (
                    existing.action
                    == AIProposal.Action.UPDATE
                ):

                    existing_data["challenge_id"] = (
                        existing.challenge_id
                    )

            if (
                reply.text != data["text"]
                or existing_data != proposed
            ):
                raise WorkflowConflict()

            return Response(
                MessageSerializer(reply).data
            )

        challenge = None

        if proposed:

            challenge, _ = validate_proposal(
                user=user,
                proposal=proposed,
            )

        reply = AIMessage.objects.create(
            conversation=message.conversation,
            reply_to=message,
            text=data["text"],
        )

        if proposed:

            AIProposal.objects.create(
                message=reply,
                action=proposed["action"],
                challenge=challenge,
                changes=proposed["changes"],
                expires_at=(
                    timezone.now()
                    + timedelta(hours=24)
                ),
            )

        return Response(
            MessageSerializer(reply).data,
            status=201,
        )


urlpatterns = [
    path("reports/users/", ReportUsers.as_view(), name="workflow-report-users"),
    path("reports/users/<int:user_id>/<str:period>/", ReportContext.as_view(), name="workflow-report-context"),
    path("reports/<int:pk>/delivery/", ReportDelivery.as_view(), name="workflow-report-delivery"),
    path("coach/queue/", CoachQueue.as_view(), name="workflow-coach-queue"),
    path("coach/messages/<int:pk>/", CoachContext.as_view(), name="workflow-coach-context"),
    path(
        "reports/<int:pk>/recipient/",
        ReportRecipient.as_view(),
        name="workflow-report-recipient",
    ),
]
