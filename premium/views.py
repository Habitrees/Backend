from django.shortcuts import render

# Create your views here.
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import extend_schema

from .models import Subscription

from .serializers import (
    PremiumStatusSerializer,
    SubscriptionSerializer,
)

from .services import (
    get_premium_status,
    activate_premium,
)

@extend_schema(tags=["Premium"])
class PremiumStatusView(APIView):

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=PremiumStatusSerializer)
    def get(self, request):

        return Response(
            PremiumStatusSerializer(
                get_premium_status(request.user)
            ).data
        )

@extend_schema(tags=["Premium"])
class PremiumActivateView(APIView):

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None,
        responses={
            200: SubscriptionSerializer,
            201: SubscriptionSerializer,
        },
    )
    def post(self, request):

        subscription, created = activate_premium(
            request.user
        )

        return Response(
            SubscriptionSerializer(subscription).data,
            status=(
                status.HTTP_201_CREATED
                if created else status.HTTP_200_OK
            ),
        )

@extend_schema(tags=["Premium"])
class PremiumHistoryView(generics.ListAPIView):

    permission_classes = [IsAuthenticated]
    serializer_class = SubscriptionSerializer
    queryset = Subscription.objects.none()

    def get_queryset(self):

        if getattr(self, "swagger_fake_view", False):
            return self.queryset

        return Subscription.objects.filter(
            user=self.request.user
        ).order_by("-activated_at")