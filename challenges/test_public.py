from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from .models import Challenge, PublicChallenge


class PublicChallengeTests(APITestCase):
    def test_filters_publication_and_idempotent_join(self):
        template = PublicChallenge.objects.create(
            title="Walk", kind=Challenge.Kind.BINARY, category="activity",
            difficulty=PublicChallenge.Difficulty.values[0], duration_days=12, published=True,
        )
        unpublished = PublicChallenge.objects.create(
            title="Draft", kind=Challenge.Kind.BINARY, category="activity",
            difficulty=template.difficulty, duration_days=12, published=False,
        )
        base = "/api/public-challenges/"
        self.assertEqual(self.client.get(base).status_code, 401)
        self.client.force_authenticate(get_user_model().objects.create(
            phone="+15550000001", username="participant", full_name="Participant",
            terms_accepted_at=timezone.now(),
        ))
        response = self.client.get(base, {
            "category": "activity", "difficulty": template.difficulty,
            "duration_days": 12, "ordering": "newest",
        })
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([row["id"] for row in response.data["results"]], [template.pk])
        self.assertEqual(self.client.get(base, {"min_duration_days": 15, "max_duration_days": 5}).status_code, 400)
        self.assertEqual(self.client.get(f"{base}{template.pk}/").status_code, 200)
        self.assertEqual(self.client.get(f"{base}{unpublished.pk}/").status_code, 404)
        self.assertEqual(self.client.post(f"{base}{unpublished.pk}/join/").status_code, 404)
        join = f"{base}{template.pk}/join/"
        first = self.client.post(join)
        self.assertEqual(first.status_code, 201, first.data)
        retry = self.client.post(join)
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(first.data["id"], retry.data["id"])
        template.refresh_from_db()
        self.assertEqual(template.popularity, 1)
