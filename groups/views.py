
from rest_framework import (
    mixins,
    status,
    viewsets,
)

from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from drf_spectacular.utils import (
    extend_schema,
    OpenApiParameter,
)
from drf_spectacular.types import OpenApiTypes

from .models import (
    HabitGroup,
    GroupMembership,
)

from .serializers import (
    GroupSerializer,
    PublicGroupSerializer,
    GroupMembershipSerializer,
    JoinGroupSerializer,
    AddMemberSerializer,
    UpdateMemberSerializer,
)

from .services import (
    create_group,
    update_group,
    join_public_group,
    add_group_member,
    update_group_member,
    remove_group_member,
    leave_group,
)

@extend_schema(tags=["Groups"])
class GroupViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):

    serializer_class = GroupSerializer

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
            return HabitGroup.objects.none()

        if not self.request.user.is_authenticated:
            return HabitGroup.objects.none()

        return HabitGroup.objects.filter(
            memberships__user=self.request.user,
        )

    def perform_create(self, serializer):

        serializer.instance = create_group(
            user=self.request.user,
            data=serializer.validated_data,
        )

    def perform_update(self, serializer):

        serializer.instance = update_group(
            user=self.request.user,
            group=serializer.instance,
            data=serializer.validated_data,
        )

    @extend_schema(
        summary="Discover Public Group",
        parameters=[
            OpenApiParameter(
                name="public_id",
                type=OpenApiTypes.UUID,
                required=True,
                description="Public group identifier",
            )
        ],
        responses={
            200: PublicGroupSerializer,
            400: dict,
            404: dict,
        },
    )
    @action(
        detail=False,
        methods=["get"],
        url_path="discover",
    )
    def discover(self, request):

        serializer = JoinGroupSerializer(
            data=request.query_params
        )

        serializer.is_valid(
            raise_exception=True
        )

        group = HabitGroup.objects.filter(
            public_id=(
                serializer.validated_data["public_id"]
            ),
            visibility=HabitGroup.Visibility.PUBLIC,
        ).first()

        if group is None:
            raise NotFound("گروه عمومی یافت نشد.")

        return Response(
            PublicGroupSerializer(group).data
        )

    @extend_schema(
        summary="Join Public Group",
        request=JoinGroupSerializer,
        responses={
            200: GroupMembershipSerializer,
            404: dict,
        },
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="join",
    )
    def join(self, request):

        serializer = JoinGroupSerializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        membership = join_public_group(
            user=request.user,
            **serializer.validated_data,
        )

        return Response(
            GroupMembershipSerializer(membership).data
        )

    @extend_schema(
        summary="Leave Group",
        request=None,
        responses={204: None, 400: dict},
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="leave",
    )
    def leave(self, request, pk=None):

        group = self.get_object()

        leave_group(
            user=request.user,
            group=group,
        )

        return Response(
            status=status.HTTP_204_NO_CONTENT
        )

    @extend_schema(
        summary="List Group Members",
        responses={
            200: GroupMembershipSerializer(many=True)
        },
    )
    @action(
        detail=True,
        methods=["get"],
        url_path="members",
    )
    def members(self, request, pk=None):

        group = self.get_object()

        memberships = (
            group.memberships.select_related("user")
        )

        return Response(
            GroupMembershipSerializer(
                memberships,
                many=True,
            ).data
        )

    @extend_schema(
        summary="Add Group Member",
        request=AddMemberSerializer,
        responses={
            201: GroupMembershipSerializer,
            400: dict,
            403: dict,
            404: dict,
        },
    )
    @members.mapping.post
    def add_member(self, request, pk=None):

        group = self.get_object()

        serializer = AddMemberSerializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        membership = add_group_member(
            actor=request.user,
            group=group,
            **serializer.validated_data,
        )

        return Response(
            GroupMembershipSerializer(membership).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        summary="Update Group Member Permissions",
        request=UpdateMemberSerializer,
        parameters=[
            OpenApiParameter(
                name="user_id",
                type=int,
                location=OpenApiParameter.PATH,
                required=True,
            )
        ],
        responses={
            200: GroupMembershipSerializer,
            400: dict,
            403: dict,
            404: dict,
        },
    )
    @action(
        detail=True,
        methods=["patch"],
        url_path=r"members/(?P<user_id>[0-9]+)",
    )
    def update_member(
        self,
        request,
        pk=None,
        user_id=None,
    ):

        group = self.get_object()

        serializer = UpdateMemberSerializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        membership = update_group_member(
            actor=request.user,
            group=group,
            user_id=user_id,
            data=serializer.validated_data,
        )

        return Response(
            GroupMembershipSerializer(membership).data
        )

    @extend_schema(
        summary="Remove Group Member",
        parameters=[
            OpenApiParameter(
                name="user_id",
                type=int,
                location=OpenApiParameter.PATH,
                required=True,
            )
        ],
        responses={
            204: None,
            403: dict,
            404: dict,
        },
    )
    @update_member.mapping.delete
    def remove_member(
        self,
        request,
        pk=None,
        user_id=None,
    ):

        group = self.get_object()

        remove_group_member(
            actor=request.user,
            group=group,
            user_id=user_id,
        )

        return Response(
            status=status.HTTP_204_NO_CONTENT
        )