

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.conf import settings
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from accounts.models import OTPChallenge, User

pytestmark = pytest.mark.django_db

PHONE = "+989123456789"
NEW_PHONE = "+989123456788"
OLD_PASSWORD = "Habitree@2026Pass"
NEW_PASSWORD = "Changed@2026Pass"
REG_PASSWORD = "Strong@2026Pass"
OTP = "123456"


@pytest.fixture(autouse=True)
def reset_throttle_cache():
    """Prevent IP-based throttles in one test from affecting other tests."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def csrf_client():
    return APIClient(enforce_csrf_checks=True)


@pytest.fixture
def verified_user():
    return User.objects.create_user(
        phone=PHONE,
        username="habitree_user",
        full_name="Habitree Test User",
        password=OLD_PASSWORD,
        phone_verified_at=timezone.now(),
        terms_version="v1",
        terms_accepted_at=timezone.now(),
        is_active=True,
    )


@pytest.fixture
def fixed_otp(monkeypatch):
    """Replace the generated random code; never send real SMS."""
    monkeypatch.setattr("accounts.views.secrets.randbelow", lambda n: int(OTP))
    with patch("accounts.views.send_otp_sms") as send_sms:
        yield send_sms


def url(name):
    return reverse(name)


def csrf_token(client):
    response = client.get(url("csrf-token"))
    assert response.status_code == 200
    return response.data["csrfToken"]


def register_send(client, phone=NEW_PHONE):
    return client.post(url("register-send-otp"), {"phone": phone}, format="json")


def register_verify(client, phone=NEW_PHONE, code=OTP):
    return client.post(
        url("register-verify-otp"), {"phone": phone, "code": code},
        format="json",
    )


def register_complete(client, registration_token, csrf=None, **overrides):
    payload = {
        "registration_token": registration_token,
        "username": "brand_new_user",
        "full_name": "Brand New User",
        "password": REG_PASSWORD,
        "confirm_password": REG_PASSWORD,
        "terms_accepted": True,
    }
    payload.update(overrides)
    extra = {"HTTP_X_CSRFTOKEN": csrf} if csrf else {}
    return client.post(url("register-complete"), payload, format="json", **extra)


def login(client, remember_me=False, password=OLD_PASSWORD, phone=PHONE, csrf=None):
    extra = {"HTTP_X_CSRFTOKEN": csrf} if csrf else {}
    return client.post(
        url("login"),
        {"phone": phone, "password": password, "remember_me": remember_me},
        format="json",
        **extra,
    )


def reset_send(client, phone=PHONE):
    return client.post(
        url("password-reset-send-otp"), {"phone": phone}, format="json"
    )


def reset_verify(client, code=OTP, phone=PHONE):
    return client.post(
        url("password-reset-verify-otp"),
        {"phone": phone, "code": code}, format="json",
    )


def reset_confirm(client, token, new_password=NEW_PASSWORD):
    return client.post(
        url("password-reset-confirm"),
        {
            "reset_token": token,
            "new_password": new_password,
            "confirm_password": new_password,
        },
        format="json",
    )


def make_reset_token(client):
    sent = reset_send(client)
    assert sent.status_code == 200
    verified = reset_verify(client)
    assert verified.status_code == 200
    return verified.data["reset_token"]


# -------- Register --------


def test_registration_happy_path(csrf_client, fixed_otp):
    token_csrf = csrf_token(csrf_client)
    sent = register_send(csrf_client)
    assert sent.status_code == 200
    fixed_otp.assert_called_once_with(NEW_PHONE, OTP)

    challenge = OTPChallenge.objects.get(
        phone=NEW_PHONE, purpose=OTPChallenge.Purpose.REGISTER
    )
    assert challenge.code_hash != OTP  # OTP is hashed at rest

    verified = register_verify(csrf_client)
    assert verified.status_code == 200
    token = verified.data["registration_token"]
    assert token

    complete = register_complete(csrf_client, token, token_csrf)
    assert complete.status_code == 201
    assert "access" in complete.data
    user = User.objects.get(phone=NEW_PHONE)
    assert user.phone_verified_at is not None
    assert user.check_password(REG_PASSWORD)
    assert complete.cookies[settings.AUTH_REFRESH_COOKIE_NAME]["httponly"]
    challenge.refresh_from_db()
    assert challenge.consumed_at is not None


def test_registration_rejects_wrong_otp(api_client, fixed_otp):
    assert register_send(api_client).status_code == 200
    assert register_verify(api_client, code="000000").status_code == 400
    assert not User.objects.filter(phone=NEW_PHONE).exists()


def test_registration_rejects_expired_otp(api_client, fixed_otp):
    assert register_send(api_client).status_code == 200
    OTPChallenge.objects.filter(
        phone=NEW_PHONE, purpose=OTPChallenge.Purpose.REGISTER
    ).update(expires_at=timezone.now() - timedelta(seconds=1))
    assert register_verify(api_client).status_code == 400


def test_registration_token_cannot_be_reused(csrf_client, fixed_otp):
    token_csrf = csrf_token(csrf_client)
    assert register_send(csrf_client).status_code == 200
    token = register_verify(csrf_client).data["registration_token"]
    assert register_complete(csrf_client, token, token_csrf).status_code == 201
    assert register_complete(
        csrf_client, token, token_csrf, username="another_new_user"
    ).status_code == 400


def test_registration_rejects_weak_password(csrf_client, fixed_otp):
    token_csrf = csrf_token(csrf_client)
    assert register_send(csrf_client).status_code == 200
    token = register_verify(csrf_client).data["registration_token"]
    response = register_complete(
        csrf_client, token, token_csrf,
        password="12345678", confirm_password="12345678",
    )
    assert response.status_code == 400
    assert not User.objects.filter(phone=NEW_PHONE).exists()


def test_registration_complete_requires_csrf(csrf_client, fixed_otp):
    assert register_send(csrf_client).status_code == 200
    token = register_verify(csrf_client).data["registration_token"]
    response = register_complete(csrf_client, token)
    assert response.status_code == 403


# -------- Login + Remember Me --------


def test_login_returns_access_and_http_only_refresh(api_client, verified_user):
    response = login(api_client)
    assert response.status_code == 200
    assert int(AccessToken(response.data["access"])['user_id']) == verified_user.pk
    cookie = response.cookies[settings.AUTH_REFRESH_COOKIE_NAME]
    assert cookie["httponly"]
    assert cookie["path"] == settings.AUTH_REFRESH_COOKIE_PATH
    assert cookie.value  # refresh token is present


def test_login_rejects_wrong_password(api_client, verified_user):
    assert login(api_client, password="incorrect-password").status_code == 400


def test_login_rejects_unverified_phone(api_client, verified_user):
    verified_user.phone_verified_at = None
    verified_user.save(update_fields=["phone_verified_at"])
    assert login(api_client).status_code == 400


@pytest.mark.parametrize("remember_me,expected_seconds,persistent", [
    (False, 12 * 60 * 60, False),
    (True, 7 * 24 * 60 * 60, True),
])
def test_remember_me_changes_cookie_and_jwt_lifetime(
    api_client, verified_user, remember_me, expected_seconds, persistent
):
    response = login(api_client, remember_me=remember_me)
    assert response.status_code == 200
    cookie = response.cookies[settings.AUTH_REFRESH_COOKIE_NAME]
    refresh = RefreshToken(cookie.value)
    lifetime = int(refresh["exp"]) - int(refresh["iat"])
    assert abs(lifetime - expected_seconds) <= 5
    if persistent:
        assert int(cookie["max-age"]) == settings.AUTH_REFRESH_COOKIE_MAX_AGE
    else:
        assert not cookie["max-age"]  # session cookie


# -------- Refresh + Logout --------


def test_refresh_returns_new_access(csrf_client, verified_user):
    csrf = csrf_token(csrf_client)
    assert login(csrf_client, csrf=csrf).status_code == 200
    response = csrf_client.post(
        url("token-refresh"), {}, format="json", HTTP_X_CSRFTOKEN=csrf
    )
    assert response.status_code == 200
    assert "access" in response.data
    assert int(AccessToken(response.data["access"])["user_id"]) == verified_user.pk


def test_logout_blacklists_refresh(csrf_client, verified_user):
    csrf = csrf_token(csrf_client)
    assert login(csrf_client, csrf=csrf).status_code == 200
    old_refresh = csrf_client.cookies[settings.AUTH_REFRESH_COOKIE_NAME].value

    logout = csrf_client.post(
        url("token-blacklist"), {}, format="json", HTTP_X_CSRFTOKEN=csrf
    )
    assert logout.status_code == 200
    assert logout.cookies[settings.AUTH_REFRESH_COOKIE_NAME].value == ""

    # Even if an attacker replays the old cookie, it should not be accepted.
    csrf_client.cookies[settings.AUTH_REFRESH_COOKIE_NAME] = old_refresh
    replay = csrf_client.post(
        url("token-refresh"), {}, format="json", HTTP_X_CSRFTOKEN=csrf
    )
    assert replay.status_code == 401


def test_logout_requires_csrf(csrf_client, verified_user):
    csrf = csrf_token(csrf_client)
    assert login(csrf_client, csrf=csrf).status_code == 200
    assert csrf_client.post(url("token-blacklist"), {}, format="json").status_code == 403


# -------- Password Reset --------


def test_reset_send_does_not_disclose_account_existence(
    api_client, verified_user, fixed_otp
):
    known = reset_send(api_client, phone=PHONE)
    unknown = reset_send(api_client, phone=NEW_PHONE)
    assert known.status_code == unknown.status_code == 200
    assert known.data == unknown.data
    fixed_otp.assert_called_once_with(PHONE, OTP)


def test_password_reset_happy_path(api_client, verified_user, fixed_otp):
    token = make_reset_token(api_client)
    response = reset_confirm(api_client, token)
    assert response.status_code == 200
    verified_user.refresh_from_db()
    assert verified_user.check_password(NEW_PASSWORD)
    assert not verified_user.check_password(OLD_PASSWORD)

    # The same reset token must be single-use.
    assert reset_confirm(api_client, token).status_code == 400
    assert login(api_client, password=NEW_PASSWORD).status_code == 200
    assert login(api_client, password=OLD_PASSWORD).status_code == 400


def test_password_reset_rejects_incorrect_otp(api_client, verified_user, fixed_otp):
    assert reset_send(api_client).status_code == 200
    assert reset_verify(api_client, code="000000").status_code == 400


def test_password_reset_rejects_expired_otp(api_client, verified_user, fixed_otp):
    assert reset_send(api_client).status_code == 200
    OTPChallenge.objects.filter(
        user=verified_user,
        purpose=OTPChallenge.Purpose.PASSWORD_RESET,
    ).update(expires_at=timezone.now() - timedelta(seconds=1))
    assert reset_verify(api_client).status_code == 400


def test_reset_invalidates_previous_refresh_tokens(
    csrf_client, verified_user, fixed_otp
):
    csrf = csrf_token(csrf_client)
    assert login(csrf_client, csrf=csrf).status_code == 200
    old_refresh = csrf_client.cookies[settings.AUTH_REFRESH_COOKIE_NAME].value
    token = make_reset_token(csrf_client)
    assert reset_confirm(csrf_client, token).status_code == 200
    csrf_client.cookies[settings.AUTH_REFRESH_COOKIE_NAME] = old_refresh
    response = csrf_client.post(
        url("token-refresh"), {}, format="json", HTTP_X_CSRFTOKEN=csrf
    )
    assert response.status_code == 401


def test_password_reset_send_throttled_at_5_per_hour(api_client):
    """Nonexistent phone avoids SMS and exercises only the per-IP throttle."""
    for _ in range(5):
        assert reset_send(api_client, phone=NEW_PHONE).status_code == 200
    assert reset_send(api_client, phone=NEW_PHONE).status_code == 429


def test_reset_confirm_rejects_invalid_token(api_client):
    assert reset_confirm(api_client, token="tampered-token").status_code == 400


def test_password_reset_verify_throttled_at_5_per_minute(
    api_client, verified_user, fixed_otp
):
    assert reset_send(api_client).status_code == 200
    for _ in range(5):
        assert reset_verify(api_client, code="000000").status_code == 400
    assert reset_verify(api_client, code="000000").status_code == 429


def test_password_reset_confirm_throttled_at_5_per_minute(api_client):
    for _ in range(5):
        assert reset_confirm(api_client, token="not-a-real-token").status_code == 400
    assert reset_confirm(api_client, token="not-a-real-token").status_code == 429
