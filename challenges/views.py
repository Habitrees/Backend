from django.shortcuts import render

# Create your views here.

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from drf_spectacular.utils import extend_schema

from .models import Challenge
from .serializers import ChallengeSerializer
from .services import (
    create_challenge,
    archive_challenge,
)


@extend_schema(tags=["Challenges"])
class ChallengeViewSet(viewsets.ModelViewSet):

    serializer_class = ChallengeSerializer

    permission_classes = [
        IsAuthenticated,
    ]

    http_method_names = [
        "get",
        "post",
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
