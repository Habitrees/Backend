
from Backend.pagination import OptionalPagination

from rest_framework import (
    serializers,
    status,
    viewsets,
)

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
)

from .models import Reminder

from .serializers import (
    ReminderSerializer,
    NotificationPreferenceSerializer,
)

from .services import (
    create_reminder,
    update_reminder,
    get_notification_preferences,
    update_notification_preferences,
)

@extend_schema(tags=["Reminders"])
@extend_schema_view(
    list=extend_schema(
        summary="List User Reminders",
        parameters=[
            OpenApiParameter(
                name="challenge",
                type=int,
                required=False,
                description="Filter by challenge ID",
            )
        ],
    ),
    create=extend_schema(
        summary="Create Reminder"
    ),
    retrieve=extend_schema(
        summary="Get Reminder"
    ),
    partial_update=extend_schema(
        summary="Update Reminder"
    ),
    destroy=extend_schema(
        summary="Delete Reminder"
    ),
)
class ReminderViewSet(viewsets.ModelViewSet):

    pagination_class = OptionalPagination
    serializer_class = ReminderSerializer

    permission_classes = [IsAuthenticated]

    http_method_names = [
        "get",
        "post",
        "patch",
        "delete",
        "head",
        "options",
    ]

    def get_queryset(self):

        if getattr(
            self,
            "swagger_fake_view",
            False,
        ):

            return Reminder.objects.none()

        if not self.request.user.is_authenticated:

            return Reminder.objects.none()

        queryset = Reminder.objects.filter(
            challenge__owner=self.request.user,
            challenge__archived=False,
        ).select_related(
            "challenge"
        )

        if self.action == "list":

            challenge_id = (
                self.request.query_params
                .get("challenge")
            )

            if challenge_id is not None:

                challenge_id = (
                    serializers.IntegerField(
                        min_value=1,
                        max_value=9223372036854775807,
                    ).run_validation(challenge_id)
                )

                queryset = queryset.filter(
                    challenge_id=challenge_id
                )

        return queryset

    def perform_create(self, serializer):

        serializer.instance = create_reminder(
            user=self.request.user,
            data=serializer.validated_data,
        )

    def perform_update(self, serializer):

        serializer.instance = update_reminder(
            user=self.request.user,
            reminder=serializer.instance,
            data=serializer.validated_data,
        )

@extend_schema(tags=["Notifications"])
class NotificationPreferenceView(APIView):

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get Notification Preferences",
        responses={
            200: NotificationPreferenceSerializer,
        },
    )
    def get(self, request):

        preference = (
            get_notification_preferences(
                user=request.user
            )
        )

        serializer = (
            NotificationPreferenceSerializer(
                preference
            )
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        summary="Update Notification Preferences",
        request=NotificationPreferenceSerializer,
        responses={
            200: NotificationPreferenceSerializer,
            400: dict,
        },
    )
    def patch(self, request):

        serializer = (
            NotificationPreferenceSerializer(
                data=request.data,
                partial=True,
            )
        )

        serializer.is_valid(
            raise_exception=True
        )

        preference = (
            update_notification_preferences(
                user=request.user,
                data=serializer.validated_data,
            )
        )

        return Response(
            NotificationPreferenceSerializer(
                preference
            ).data,
            status=status.HTTP_200_OK,
        )