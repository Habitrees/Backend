from rest_framework.routers import SimpleRouter

from .views import GroupViewSet

router = SimpleRouter()

router.register(
    r"groups",
    GroupViewSet,
    basename="group",
)

urlpatterns = router.urls