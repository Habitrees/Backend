from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from Backend.pagination import StandardPagination
from .models import PublicChallenge
from .serializers import (
    ChallengeSerializer, PublicChallengeFilterSerializer, PublicChallengeSerializer,
)
from .services import join_public_challenge


@extend_schema_view(list=extend_schema(parameters=[PublicChallengeFilterSerializer]))
class PublicChallengeViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                             viewsets.GenericViewSet):
    queryset = PublicChallenge.objects.filter(published=True)
    serializer_class = PublicChallengeSerializer
    pagination_class = StandardPagination
    ordering_fields = {
        "popular": ("-popularity", "-pk"),
        "newest": ("-created_at", "-pk"),
        "duration_asc": ("duration_days", "pk"),
        "duration_desc": ("-duration_days", "-pk"),
    }

    def get_queryset(self):
        if self.action != "list":
            return self.queryset
        filters = PublicChallengeFilterSerializer(data=self.request.query_params)
        filters.is_valid(raise_exception=True)
        data = dict(filters.validated_data)
        ordering = data.pop("ordering")
        minimum = data.pop("min_duration_days", 1)
        maximum = data.pop("max_duration_days", 366)
        if minimum > maximum:
            raise ValidationError({"max_duration_days": "Must be at least the minimum."})
        return self.queryset.filter(
            duration_days__range=(minimum, maximum), **data
        ).order_by(*self.ordering_fields[ordering])

    @extend_schema(request=None, responses={200: ChallengeSerializer, 201: ChallengeSerializer})
    @action(detail=True, methods=["post"])
    def join(self, request, pk=None):
        template = self.get_object()
        challenge, created = join_public_challenge(
            user=request.user, public_challenge_id=template.pk,
        )
        return Response(ChallengeSerializer(challenge).data, status=201 if created else 200)
