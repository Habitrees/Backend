import logging

from django.db import connections
from django.http import JsonResponse
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is not None:
        return response
    for connection in connections.all(initialized_only=True):
        if connection.in_atomic_block:
            connection.set_rollback(True)
    logger.error(
        "api_request_failed view=%s method=%s error_type=%s",
        type(context.get("view")).__name__, context["request"].method, type(exc).__name__,
    )
    return Response({"detail": "Internal server error."}, status=500)


def server_error(request):
    return JsonResponse({"detail": "Internal server error."}, status=500)
