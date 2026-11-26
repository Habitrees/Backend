from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from challenges.models import Challenge
from .models import AIProposal


@override_settings(N8N_COACH_TOKEN="coach-test", N8N_REPORT_TOKEN="report-test")
class CoachTests(APITestCase):
    def setUp(self):
        self.owner, self.other = [
            get_user_model().objects.create(
                phone=f"+1555000000{n}", username=f"coach{n}", full_name="Member",
                terms_accepted_at=timezone.now(), ai_coach_enabled=(n == 2),
            ) for n in (1, 2)
        ]

    def test_consent_scope_validation_and_idempotent_decisions(self):
        base = "/api/coach/conversations/"
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.post(base, {"title": "Plan"}).status_code, 403)
        self.assertEqual(self.client.patch(
            "/api/auth/profile/", {"ai_coach_enabled": True},
        ).status_code, 200)
        self.owner.refresh_from_db()
        conversation = self.client.post(base, {"title": "Plan"})
        self.assertEqual(conversation.status_code, 201, conversation.data)
        url = f"{base}{conversation.data['id']}/"
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_authenticate(self.owner)
        message = self.client.post(f"{url}messages/", {"text": "New title please"})
        self.assertEqual(message.status_code, 201, message.data)
        challenge = Challenge.objects.create(
            owner=self.owner, title="Before", kind="binary",
            start_date=timezone.localdate(), duration_days=10,
        )
        callback = f"/api/internal/n8n/coach/messages/{message.data['id']}/"
        payload = {
            "text": "Try a clearer title",
            "proposal": {"challenge_id": challenge.pk, "changes": {"title": "After"}},
        }
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post(
            callback, payload, format="json", HTTP_X_WORKFLOW_TOKEN="report-test",
        ).status_code, 403)
        self.assertEqual(self.client.get(
            callback, HTTP_X_WORKFLOW_TOKEN="coach-test",
        ).status_code, 200)
        invalid = {**payload, "proposal": {**payload["proposal"], "changes": {"archived": True}}}
        self.assertEqual(self.client.post(
            callback, invalid, format="json", HTTP_X_WORKFLOW_TOKEN="coach-test",
        ).status_code, 400)
        first = self.client.post(callback, payload, format="json", HTTP_X_WORKFLOW_TOKEN="coach-test")
        self.assertEqual(first.status_code, 201, first.data)
        repeated = self.client.post(callback, payload, format="json", HTTP_X_WORKFLOW_TOKEN="coach-test")
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(first.data["id"], repeated.data["id"])
        challenge.refresh_from_db()
        self.assertEqual(challenge.title, "Before")
        proposal = AIProposal.objects.get(pk=first.data["proposal_id"])
        decision = f"/api/coach/proposals/{proposal.pk}/"
        self.client.force_authenticate(self.owner)
        expiry = proposal.expires_at
        AIProposal.objects.filter(pk=proposal.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.post(f"{decision}accept/").status_code, 409)
        AIProposal.objects.filter(pk=proposal.pk).update(expires_at=expiry)
        self.assertEqual(self.client.post(f"{decision}accept/").status_code, 200)
        self.assertEqual(self.client.post(f"{decision}accept/").status_code, 200)
        self.assertEqual(self.client.post(f"{decision}reject/").status_code, 409)
        challenge.refresh_from_db()
        self.assertEqual(challenge.title, "After")
        proposal.refresh_from_db()
        self.assertIsNotNone(proposal.decided_at)
