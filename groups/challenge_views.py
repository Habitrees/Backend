
from datetime import date

from Backend.pagination import OptionalPagination

from rest_framework import (
    mixins,
    status,
    viewsets,
)

from rest_framework.decorators import action
from rest_framework.exceptions import (
    NotFound,
    ValidationError,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from drf_spectacular.utils import (
    extend_schema,
    OpenApiParameter,
)

from challenges.schedule import (
    get_local_today,
    get_period,
)

from challenges.serializers import (
    HabitLogInputSerializer,
    ScheduleSerializer,
)

from .models import (
    GroupMembership,
    GroupChallenge,
    GroupHabitLog,
    GroupWarning,
)

from .serializers import (
    GroupChallengeSerializer,
    GroupHabitLogSerializer,
    GroupMemberProgressSerializer,
    GroupWarningSerializer,
    ApplyPolicySerializer,
    PolicyResultSerializer,
)

from .services import get_membership

from .challenge_services import (
    create_group_challenge,
    update_group_challenge,
    record_group_log,
    get_group_progress,
    apply_failure_policy,
)

@extend_schema(
    tags=["Group Challenges"],
    parameters=[
        OpenApiParameter(
            name="group_id",
            type=int,
            location=OpenApiParameter.PATH,
            required=True,
        )
    ],
)
class GroupChallengeViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):

    queryset = GroupChallenge.objects.none()

    pagination_class = OptionalPagination
    serializer_class = GroupChallengeSerializer

    permission_classes = [IsAuthenticated]

    http_method_names = [
        "get",
        "post",
        "put",
        "patch",
        "head",
        "options",
    ]

    def get_queryset(self):

        if getattr(
            self,
            "swagger_fake_view",
            False,
        ):
            return GroupChallenge.objects.none()

        if not self.request.user.is_authenticated:
            return GroupChallenge.objects.none()

        group_id = self.kwargs.get("group_id")

        if not GroupMembership.objects.filter(
            group_id=group_id,
            user=self.request.user,
        ).exists():

            raise NotFound("گروه یافت نشد.")

        return GroupChallenge.objects.filter(
            group_id=group_id,
        ).select_related("group")

    def perform_create(self, serializer):

        serializer.instance = create_group_challenge(
            user=self.request.user,
            group_id=self.kwargs["group_id"],
            data=serializer.validated_data,
        )

    def perform_update(self, serializer):

        serializer.instance = update_group_challenge(
            user=self.request.user,
            challenge=serializer.instance,
            data=serializer.validated_data,
        )

    @extend_schema(exclude=True)
    def update(self, request, *args, **kwargs):

        if not kwargs.get("partial", False):

            from rest_framework.exceptions import (
                MethodNotAllowed,
            )

            raise MethodNotAllowed("PUT")

        return super().update(
            request,
            *args,
            **kwargs,
        )

    @extend_schema(
        summary="Get Group Challenge Schedule",
        responses={200: ScheduleSerializer},
    )
    @action(
        detail=True,
        methods=["get"],
        url_path="schedule",
    )
    def schedule(
        self, request, pk=None, group_id=None
    ):

        challenge = self.get_object()

        today = get_local_today(challenge)

        period = get_period(
            challenge,
            today,
        )

        data = {
            "frequency": challenge.frequency,
            "today": today,
            "start_date": challenge.start_date,
            "end_date": challenge.end_date,

            "current_period_start":
                period[0] if period else None,

            "current_period_end":
                period[1] if period else None,
        }

        return Response(
            ScheduleSerializer(data).data
        )

    @extend_schema(
        summary="Get My Group Habit Logs",
        responses={
            200: GroupHabitLogSerializer(many=True)
        },
    )
    @action(
        detail=True,
        methods=["get"],
        url_path="logs",
        pagination_class=None,
    )
    def logs(
        self, request, pk=None, group_id=None
    ):

        challenge = self.get_object()

        membership = get_membership(
            challenge.group,
            request.user,
        )

        logs = GroupHabitLog.objects.filter(
            challenge=challenge,
            membership=membership,
        )

        return Response(
            GroupHabitLogSerializer(
                logs,
                many=True,
            ).data
        )

    @extend_schema(
        summary="Record Group Habit Log",
        request=HabitLogInputSerializer,
        responses={
            200: GroupHabitLogSerializer,
            201: GroupHabitLogSerializer,
            400: dict,
        },
    )
    @action(
        detail=True,
        methods=["put"],
        url_path=r"logs/(?P<log_date>\d{4}-\d{2}-\d{2})",
    )
    def record_log(
        self,
        request,
        pk=None,
        group_id=None,
        log_date=None,
    ):

        challenge = self.get_object()

        try:
            period_start = date.fromisoformat(
                log_date
            )

        except (ValueError, TypeError):

            raise ValidationError({
                "date": "تاریخ معتبر نیست."
            })

        serializer = HabitLogInputSerializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        log, created = record_group_log(
            user=request.user,
            challenge=challenge,
            period_start=period_start,
            **serializer.validated_data,
        )

        return Response(
            GroupHabitLogSerializer(log).data,
            status=(
                status.HTTP_201_CREATED
                if created
                else status.HTTP_200_OK
            ),
        )

    @extend_schema(
        summary="Get Group Members Progress",
        responses={
            200: GroupMemberProgressSerializer(
                many=True
            )
        },
    )
    @action(
        detail=True,
        methods=["get"],
        url_path="progress",
        pagination_class=None,
    )
    def progress(
        self, request, pk=None, group_id=None
    ):

        challenge = self.get_object()

        data = get_group_progress(
            user=request.user,
            challenge=challenge,
        )

        return Response(
            GroupMemberProgressSerializer(
                data,
                many=True,
            ).data
        )

    @extend_schema(
        summary="Apply Group Failure Policy",
        request=ApplyPolicySerializer,
        responses={
            200: PolicyResultSerializer,
            400: dict,
            403: dict,
            404: dict,
        },
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="apply-policy",
    )
    def apply_policy(
        self, request, pk=None, group_id=None
    ):

        challenge = self.get_object()

        serializer = ApplyPolicySerializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        result = apply_failure_policy(
            actor=request.user,
            challenge=challenge,
            **serializer.validated_data,
        )

        return Response(
            PolicyResultSerializer(result).data
        )

    @extend_schema(
        summary="Get My Group Warnings",
        responses={
            200: GroupWarningSerializer(many=True)
        },
    )
    @action(
        detail=True,
        methods=["get"],
        url_path="warnings",
        pagination_class=None,
    )
    def warnings(
        self, request, pk=None, group_id=None
    ):

        challenge = self.get_object()

        membership = get_membership(
            challenge.group,
            request.user,
        )

        warnings = GroupWarning.objects.filter(
            challenge=challenge,
            membership=membership,
        )

        return Response(
            GroupWarningSerializer(
                warnings,
                many=True,
            ).data
        )