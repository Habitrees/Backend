from datetime import date

from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

from drf_spectacular.utils import extend_schema

from .models import Challenge

from .serializers import (
    ChallengeSerializer,
    HabitLogInputSerializer,
    HabitLogSerializer,
    ScheduleSerializer,
    DashboardSerializer,
)

from .services import (
    create_challenge,
    archive_challenge,
    record_habit_log,
    get_streak_data,
    recover_habit_log,
    get_plant_data,
    get_garden_data,
    get_dashboard_data,
)

from .schedule import (
    get_local_today,
    get_period,
)
from .serializers import (
    ChallengeSerializer,
    HabitLogInputSerializer,
    HabitLogSerializer,
    ScheduleSerializer,
    StreakSerializer,
    PlantSerializer,
    GardenSerializer,
)
from rest_framework.views import APIView

@extend_schema(tags=["Challenges"])
class ChallengeViewSet(viewsets.ModelViewSet):

    serializer_class = ChallengeSerializer

    permission_classes = [
        IsAuthenticated,
    ]

    http_method_names = [
        "get",
        "post",
        "put",
        "patch",
        "delete",
        "head",
        "options",
    ]

    def get_queryset(self):

        if getattr(self, "swagger_fake_view", False):
            return Challenge.objects.none()

        if not self.request.user.is_authenticated:
            return Challenge.objects.none()

        return Challenge.objects.filter(
            owner=self.request.user,
            archived=False,
        )

    def perform_create(self, serializer):

        serializer.instance = create_challenge(
            user=self.request.user,
            data=serializer.validated_data,
        )

    def perform_destroy(self, instance):

        archive_challenge(
            challenge=instance
        )
    
    @extend_schema(
        summary="Get Challenge Schedule",
        responses={200: ScheduleSerializer},
    )
    @action(
        detail=True,
        methods=["get"],
        url_path="schedule",
    )
    def schedule(self, request, pk=None):

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
            "current_period_start": (
                period[0] if period else None
            ),
            "current_period_end": (
                period[1] if period else None
            ),
        }

        return Response(
            ScheduleSerializer(data).data
        )

    @extend_schema(
        summary="Get Challenge Habit Logs",
        responses={
            200: HabitLogSerializer(many=True)
        },
    )
    @action(
        detail=True,
        methods=["get"],
        url_path="logs",
    )
    def logs(self, request, pk=None):

        challenge = self.get_object()

        logs = challenge.logs.all()

        serializer = HabitLogSerializer(
            logs,
            many=True,
        )

        return Response(serializer.data)

    @extend_schema(
        summary="Create or Update Habit Log",
        request=HabitLogInputSerializer,
        responses={
            200: HabitLogSerializer,
            201: HabitLogSerializer,
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

        log, created = record_habit_log(

            challenge=challenge,

            period_start=period_start,

            **serializer.validated_data,
        )

        return Response(

            HabitLogSerializer(log).data,

            status=(
                status.HTTP_201_CREATED
                if created
                else status.HTTP_200_OK
            ),
        )
    def update(self, request, *args, **kwargs):

        if not kwargs.get("partial", False):

            from rest_framework.exceptions import MethodNotAllowed

            raise MethodNotAllowed("PUT")

        return super().update(
            request,
            *args,
            **kwargs,
        )
    
    @extend_schema(
        summary="Get Challenge Streak",
        description=(
            "Returns current streak, best streak "
            "and recovery availability."
        ),
        responses={
            200: StreakSerializer,
            404: dict,
        },
    )
    @action(
        detail=True,
        methods=["get"],
        url_path="streak",
    )
    def streak(self, request, pk=None):

        challenge = self.get_object()

        data = get_streak_data(challenge)

        serializer = StreakSerializer(data)

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )
    
    @extend_schema(
        summary="Recover Missed Habit Log",
        description=(
            "Recover yesterday's missed habit "
            "in daily flexible challenges."
        ),
        request=HabitLogInputSerializer,
        responses={
            200: HabitLogSerializer,
            400: dict,
            404: dict,
        },
    )
    @action(
        detail=True,
        methods=["post"],
        url_path=r"recover/(?P<log_date>\d{4}-\d{2}-\d{2})",
    )
    def recover_log(
        self,
        request,
        pk=None,
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

        log = recover_habit_log(
            challenge=challenge,
            period_start=period_start,
            **serializer.validated_data,
        )

        return Response(
            HabitLogSerializer(log).data,
            status=status.HTTP_200_OK,
        )
    
    @extend_schema(
        summary="Get Challenge Plant",
        description=(
            "Returns plant growth stage "
            "and challenge progress."
        ),
        responses={
            200: PlantSerializer,
            404: dict,
        },
    )
    @action(
        detail=True,
        methods=["get"],
        url_path="plant",
    )
    def plant(self, request, pk=None):

        challenge = self.get_object()

        data = get_plant_data(challenge)

        return Response(
            PlantSerializer(data).data,
            status=status.HTTP_200_OK,
        )

@extend_schema(tags=["Garden"])
class GardenView(APIView):

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get User Garden",
        description=(
            "Returns growing and completed "
            "plants belonging to the current user."
        ),
        responses={
            200: GardenSerializer,
        },
    )
    def get(self, request):

        data = get_garden_data(
            user=request.user
        )

        return Response(
            GardenSerializer(data).data,
            status=status.HTTP_200_OK,
        )
    

@extend_schema(tags=["Dashboard"])
class DashboardView(APIView):

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get User Dashboard",
        description=(
            "Returns active challenges, current "
            "performance, streaks, plant progress "
            "and weekly performance statistics."
        ),
        responses={
            200: DashboardSerializer,
            401: dict,
        },
    )
    def get(self, request):

        data = get_dashboard_data(
            user=request.user
        )

        serializer = DashboardSerializer(data)

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )
