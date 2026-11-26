from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from groups.services import create_group
from .models import Challenge, PublicChallenge


class ChallengeContractTests(APITestCase):
    def test_crud_dashboard_and_permission_boundaries(self):
        owner, outsider = [
            get_user_model().objects.create(
                phone=f"+1555000000{n}", username=f"habit{n}", full_name="Member",
                terms_accepted_at=timezone.now(),
            ) for n in (1, 2)
        ]
        self.client.force_authenticate(owner)
        base = "/api/challenges/"
        today = timezone.localdate()
        created = self.client.post(base, {
            "title": "Read", "start_date": today, "duration_days": 10, "kind": "binary",
        })
        self.assertEqual(created.status_code, 201, created.data)
        pk = created.data["id"]
        detail = f"{base}{pk}/"
        self.assertEqual(self.client.get(base, {"page": 1}).data["count"], 1)
        self.assertEqual(self.client.get(detail).data["title"], "Read")
        self.assertEqual(self.client.patch(detail, {"title": "Read more"}).status_code, 200)
        self.assertEqual(self.client.put(f"{detail}logs/{today}/", {"performed": True}).status_code, 201)
        group = create_group(user=owner, data={"name": "Reading group"})
        create_group(user=outsider, data={"name": "Other group"})
        template = PublicChallenge.objects.create(
            title="Walk", kind=Challenge.Kind.BINARY, category="activity",
            difficulty=PublicChallenge.Difficulty.values[0], duration_days=12, published=True,
        )
        dashboard = self.client.get("/api/dashboard/").data
        self.assertEqual([row["id"] for row in dashboard["active_groups"]], [group.pk])
        self.assertEqual([row["id"] for row in dashboard["recommended_challenges"]], [template.pk])
        self.assertEqual(dashboard["monthly_summary"]["total_periods"], 0)
        self.client.force_authenticate(outsider)
        for response in (
            self.client.get(detail),
            self.client.patch(detail, {"title": "Unowned"}),
            self.client.delete(detail),
        ):
            self.assertEqual(response.status_code, 404)
        self.client.force_authenticate(owner)
        self.assertEqual(self.client.delete(detail).status_code, 204)
        self.assertTrue(Challenge.objects.get(pk=pk).archived)
