from unittest.mock import patch

from django.db import DatabaseError
from django.test import SimpleTestCase
from redis.exceptions import RedisError


class HealthTests(SimpleTestCase):
    def test_liveness_and_readiness(self):
        self.assertEqual(self.client.get("/health/live/").json(), {"status": "ok"})
        with patch("Backend.health.connection.cursor"), patch("Backend.health.Redis.from_url") as redis:
            redis.return_value.__enter__.return_value.ping.return_value = True
            self.assertEqual(self.client.get("/health/ready/").status_code, 200)
        with (
            patch("Backend.health.connection.cursor", side_effect=DatabaseError("private")),
            patch("Backend.health.Redis.from_url", side_effect=RedisError("private")),
        ):
            response = self.client.get("/health/ready/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unavailable", "postgres": False, "redis": False})
