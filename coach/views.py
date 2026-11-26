from django.db import transaction
from django.shortcuts import get_object_or_404
from django.urls import path
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter

from Backend.pagination import StandardPagination
from accounts.models import User
from challenges.models import Challenge
from challenges.serializers import ChallengeSerializer
from .models import AIConversation, AIProposal
from .serializers import ConversationSerializer, MessageSerializer, ProposalSerializer
from challenges.services import create_challenge
from .services import validate_proposal

class Conflict(APIException):
    status_code = 409
    default_detail = "The proposal can no longer be applied."


def require_coach(user):
    if not user.ai_coach_enabled:
        raise PermissionDenied("Enable AI Coach in your profile first.")


class ConversationViewSet(mixins.ListModelMixin, mixins.CreateModelMixin,
                          mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = ConversationSerializer
    pagination_class = StandardPagination
    queryset = AIConversation.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        require_coach(self.request.user)
        return AIConversation.objects.filter(owner=self.request.user).order_by("-pk")

    def perform_create(self, serializer):
        require_coach(self.request.user)
        serializer.save(owner=self.request.user)

    @extend_schema(responses=MessageSerializer(many=True))
    @action(detail=True, methods=["get"])
    def messages(self, request, pk=None):
        messages = self.get_object().messages.select_related("proposal").order_by("-pk")
        page = self.paginate_queryset(messages)
        return self.get_paginated_response(MessageSerializer(page, many=True).data)

    @extend_schema(request=MessageSerializer, responses={201: MessageSerializer})
    @messages.mapping.post
    def send_message(self, request, pk=None):
        conversation = self.get_object()
        serializer = MessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(conversation=conversation)
        return Response(serializer.data, status=201)


class ProposalView(generics.RetrieveAPIView):
    serializer_class = ProposalSerializer
    queryset = AIProposal.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        require_coach(self.request.user)
        return AIProposal.objects.filter(message__conversation__owner=self.request.user)


class ProposalDecisionView(ProposalView):
    http_method_names = ["post", "options"]
    decision = None

    @extend_schema(
        request=None,
        responses=ProposalSerializer,
    )
    @transaction.atomic
    def post(self, request, pk):

        user = User.objects.select_for_update().get(
            pk=request.user.pk
        )

        require_coach(user)

        proposal = get_object_or_404(
            self.get_queryset().select_for_update(),
            pk=pk,
        )

        if proposal.decision == self.decision:

            return Response(
                self.get_serializer(proposal).data
            )

        if (
            proposal.decision
            != AIProposal.Decision.PENDING
        ):

            raise Conflict(
                "A decision has already been recorded."
            )

        if self.decision == AIProposal.Decision.ACCEPTED:

            if proposal.expires_at <= timezone.now():

                raise Conflict(
                    "The proposal has expired."
                )

            data = {
                "action": proposal.action,
                "changes": proposal.changes,
            }

            if proposal.action == AIProposal.Action.UPDATE:

                data["challenge_id"] = (
                    proposal.challenge_id
                )

                if proposal.challenge_id is None:

                    raise Conflict(
                        "The challenge is unavailable."
                    )

                if not Challenge.objects.filter(
                    pk=proposal.challenge_id,
                    owner=user,
                    archived=False,
                ).exists():

                    raise Conflict(
                        "The challenge is unavailable."
                    )

            challenge, serializer = validate_proposal(
                user=user,
                proposal=data,
                lock=True,
            )

            if proposal.action == AIProposal.Action.CREATE:

                result = create_challenge(
                    user=user,
                    data=serializer.validated_data,
                )

            else:

                result = serializer.save()

            proposal.result_challenge = result

        proposal.decision = self.decision

        proposal.decided_at = timezone.now()

        proposal.save(
            update_fields=[
                "decision",
                "decided_at",
                "result_challenge",
            ]
        )

        return Response(
            self.get_serializer(proposal).data
        )


router = SimpleRouter()
router.register("conversations", ConversationViewSet, basename="coach-conversation")
urlpatterns = [
    *router.urls,
    path("proposals/<int:pk>/", ProposalView.as_view(), name="coach-proposal"),
    path("proposals/<int:pk>/accept/", ProposalDecisionView.as_view(
        decision=AIProposal.Decision.ACCEPTED,
    ), name="coach-proposal-accept"),
    path("proposals/<int:pk>/reject/", ProposalDecisionView.as_view(
        decision=AIProposal.Decision.REJECTED,
    ), name="coach-proposal-reject"),
]
