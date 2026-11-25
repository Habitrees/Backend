from rest_framework.routers import SimpleRouter

from .views import GroupViewSet
from .challenge_views import GroupChallengeViewSet

router = SimpleRouter()

router.register(
    r"groups",
    GroupViewSet,
    basename="group",
)
router.register(
    r"groups/(?P<group_id>[0-9]+)/challenges",
    GroupChallengeViewSet,
    basename="group-challenge",
)

urlpatterns = router.urls