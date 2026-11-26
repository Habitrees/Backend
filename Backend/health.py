import logging

from django.conf import settings
from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe
from redis import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


@require_safe
@never_cache
def live(request):
    return JsonResponse({"status": "ok"})


@require_safe
@never_cache
def ready(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError as error:
        logger.warning("readiness_check_failed dependency=postgres error_type=%s", type(error).__name__)
        database_ready = False
    else:
        database_ready = True
    try:
        with Redis.from_url(
            settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2,
        ) as client:
            redis_ready = bool(client.ping())
    except (RedisError, ValueError) as error:
        logger.warning("readiness_check_failed dependency=redis error_type=%s", type(error).__name__)
        redis_ready = False
    ready = database_ready and redis_ready
    return JsonResponse({
        "status": "ok" if ready else "unavailable",
        "postgres": database_ready, "redis": redis_ready,
    }, status=200 if ready else 503)
