from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from Backend.pagination import StandardPagination
from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ("id", "title", "message", "created_at", "read_at")


class MarkAllSerializer(serializers.Serializer):
    updated = serializers.IntegerField()


class NotificationViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = NotificationSerializer
    pagination_class = StandardPagination
    queryset = Notification.objects.none()

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).order_by("-pk")

    @extend_schema(request=None)
    @action(detail=True, methods=["post"], url_path="read")
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        self.get_queryset().filter(pk=notification.pk, read_at__isnull=True).update(
            read_at=timezone.now(),
        )
        notification.refresh_from_db()
        return Response(self.get_serializer(notification).data)

    @extend_schema(request=None, responses=MarkAllSerializer)
    @action(detail=False, methods=["post"], url_path="read-all")
    def mark_all_read(self, request):
        updated = self.get_queryset().filter(read_at__isnull=True).update(read_at=timezone.now())
        return Response({"updated": updated})
