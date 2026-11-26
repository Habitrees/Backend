from django.urls import path
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from .exports import csv_export, pdf_export
from .serializers import ReportQuery, ReportSerializer
from .services import PERIODS, build_report
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from Backend.pagination import StandardPagination

from .models import SmartReport
from .serializers import SmartReportSerializer

class ReportView(APIView):
    @extend_schema(parameters=[ReportQuery], responses={
        200: ReportSerializer, (200, "text/csv"): OpenApiTypes.BINARY,
        (200, "application/pdf"): OpenApiTypes.BINARY,
    })
    def get(self, request, period):
        if period not in PERIODS:
            raise NotFound()
        query = ReportQuery(data=request.query_params)
        query.is_valid(raise_exception=True)
        options = query.validated_data
        data = build_report(request.user, period, options.get("date"))
        export = options.get("export")
        if export is None:
            return Response(ReportSerializer(data).data)
        language = options.get("language", request.user.locale.split("-")[0])
        response = csv_export(data) if export == "csv" else pdf_export(data, language == "fa")
        response["Content-Disposition"] = f'attachment; filename="{period}-report.{export}"'
        return response

@extend_schema(tags=["Reports"])
class SmartReportListView(generics.ListAPIView):

    serializer_class = SmartReportSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination
    queryset = SmartReport.objects.none()

    def get_queryset(self):

        if getattr(self, "swagger_fake_view", False):
            return self.queryset

        return SmartReport.objects.filter(
            user=self.request.user
        ).order_by("-created_at", "-pk")

@extend_schema(tags=["Reports"])
class SmartReportDetailView(generics.RetrieveAPIView):

    serializer_class = SmartReportSerializer
    permission_classes = [IsAuthenticated]
    queryset = SmartReport.objects.none()

    def get_queryset(self):

        if getattr(self, "swagger_fake_view", False):
            return self.queryset

        return SmartReport.objects.filter(
            user=self.request.user
        )
urlpatterns = [
    path(
        "smart/",
        SmartReportListView.as_view(),
        name="smart-report-list",
    ),
    path(
        "smart/<int:pk>/",
        SmartReportDetailView.as_view(),
        name="smart-report-detail",
    ),
    path(
        "<str:period>/",
        ReportView.as_view(),
        name="report-detail",
    ),
]
