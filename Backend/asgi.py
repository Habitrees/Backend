
import os

from django.core.asgi import (
    get_asgi_application,
)

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "Backend.settings",
)

django_asgi_app = get_asgi_application()

from django.conf import settings

from channels.routing import (
    ProtocolTypeRouter,
    URLRouter,
)

from channels.security.websocket import (
    OriginValidator,
)

from groups.routing import (
    websocket_urlpatterns,
)

application = ProtocolTypeRouter({

    "http": django_asgi_app,

    "websocket": OriginValidator(
        URLRouter(
            websocket_urlpatterns
        ),
        settings.WEBSOCKET_ALLOWED_ORIGINS,
    ),
})