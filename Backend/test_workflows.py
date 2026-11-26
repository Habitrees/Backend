from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from notifications.models import NotificationPreference


@override_settings(N8N_REPORT_TOKEN="report-test", N8N_COACH_TOKEN="coach-test")
class ReportingWorkflowTests(APITestCase):
    def test_scope_eligibility_and_truthful_delivery_status(self):
        user, other = [
            get_user_model().objects.create(
                phone=f"+1555000000{n}", username=f"workflow{n}", full_name="Member",
                terms_accepted_at=timezone.now(),
            ) for n in (1, 2)
        ]
        NotificationPreference.objects.create(user=user, email_reports_enabled=True)
        base = "/api/internal/n8n/reports/"
        self.assertEqual(self.client.get(f"{base}users/").status_code, 403)
        self.assertEqual(self.client.get(
            f"{base}users/", HTTP_X_WORKFLOW_TOKEN="coach-test",
        ).status_code, 403)
        self.client.credentials(HTTP_X_WORKFLOW_TOKEN="report-test")
        users = self.client.get(f"{base}users/")
        self.assertEqual(users.status_code, 200, users.data)
        self.assertEqual(users.data["results"], [{"id": user.pk, "timezone": "UTC", "locale": "fa-IR"}])
        self.assertEqual(self.client.get(f"{base}users/{other.pk}/weekly/").status_code, 404)
        url = f"{base}users/{user.pk}/weekly/"
        self.assertEqual(self.client.get(url, {"date": "2026-10-05"}).status_code, 200)
        payload = {"date": "2026-10-05", "narrative": "A steady week."}
        stored = self.client.post(url, payload)
        self.assertEqual(stored.status_code, 201, stored.data)
        self.assertEqual(self.client.post(url, payload).status_code, 200)
        self.assertEqual(self.client.post(url, {**payload, "narrative": "Different"}).status_code, 409)
        delivery_url = f"{base}{stored.data['id']}/delivery/"
        failed = self.client.patch(delivery_url, {"status": "failed"})
        self.assertEqual(failed.status_code, 502, failed.data)
        self.assertEqual(failed.data["delivery_status"], "failed")
        self.assertEqual(self.client.patch(delivery_url, {"status": "delivered"}).status_code, 200)
        self.assertEqual(self.client.patch(delivery_url, {"status": "failed"}).status_code, 409)
