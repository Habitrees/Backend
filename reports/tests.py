from datetime import date, datetime, timezone as utc
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from challenges.models import Challenge, HabitLog
from .exports import pdf_export


class ReportTests(APITestCase):
    def test_report_uses_closed_schedules_and_excludes_other_users(self):
        start = date(2026, 10, 5)
        now = datetime(2026, 10, 7, 12, tzinfo=utc.utc)
        owner, other = [
            get_user_model().objects.create(
                phone=f"+1555000000{n}", username=f"report{n}", full_name="Member",
                terms_accepted_at=now,
            ) for n in (1, 2)
        ]
        challenge, _ = [
            Challenge.objects.create(
                owner=user, title="=Read", kind="binary", start_date=start, duration_days=7,
            ) for user in (owner, other)
        ]
        HabitLog.objects.create(challenge=challenge, period_start=start, performed=True, success=True)
        self.client.force_authenticate(owner)
        with patch("django.utils.timezone.now", return_value=now):
            report = self.client.get("/api/reports/weekly/")
            csv = self.client.get("/api/reports/weekly/", {"export": "csv"})
            month = self.client.get("/api/reports/monthly/")
            year = self.client.get("/api/reports/yearly/")
        self.assertEqual(report.status_code, 200, report.data)
        self.assertEqual(month.status_code, 200)
        self.assertEqual(year.status_code, 200)
        self.assertEqual(report.data["success_count"], 1)
        self.assertEqual(report.data["failure_count"], 1)
        self.assertEqual(report.data["completion_rate"], 50)
        self.assertEqual(report.data["best_streak"], 1)
        self.assertEqual(report.data["previous_period"]["success_count"], 0)
        self.assertEqual(len(report.data["challenge_performance"]), 1)
        self.assertTrue(csv["Content-Type"].startswith("text/csv"))
        self.assertIn(b"'=Read", csv.content)


class ReportPDFTests(SimpleTestCase):
    def test_renders_persian_challenge_and_right_aligns_rows(self):
        from reportlab.pdfgen.canvas import Canvas

        metrics = {"success_count": 1, "failure_count": 0, "completion_rate": 100}
        previous = {**metrics, "period_start": "2026-09-28", "period_end": "2026-10-04"}
        title = "پیاده‌روی روزانه"
        data = {
            **metrics, "period": "weekly", "period_start": "2026-10-05", "period_end": "2026-10-11",
            "previous_period": previous, "completion_rate_change": 0,
            "challenge_performance": [{**metrics, "title": title}],
        }
        with patch.object(Canvas, "drawRightString", autospec=True, side_effect=Canvas.drawRightString) as draw:
            response = pdf_export(data, rtl=True)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertTrue(any(
            any("\ufb50" <= char <= "\ufeff" for char in call.args[3])
            for call in draw.call_args_list
        ))
