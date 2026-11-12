
from django.urls import path


from .views import (
    RegisterSendOTPView,
    RegisterVerifyOTPView,
    RegisterCompleteView,
    LoginView,
    PasswordResetSendOTPView,
    PasswordResetVerifyOTPView,
    PasswordResetConfirmView,
    CsrfTokenView,
    CookieTokenRefreshView,
    CookieTokenBlacklistView,
)

urlpatterns = [
    # Registration
    path(
        "register/send-otp/",
        RegisterSendOTPView.as_view(),
        name="register-send-otp",
    ),
    path(
        "register/verify-otp/",
        RegisterVerifyOTPView.as_view(),
        name="register-verify-otp",
    ),
    path(
        "register/complete/",
        RegisterCompleteView.as_view(),
        name="register-complete",
    ),

    # Authentication
    path(
        "login/",
        LoginView.as_view(),
        name="login",
    ),
    # CSRF Token
    path(
        "csrf/",
        CsrfTokenView.as_view(),
        name="csrf-token",
    ),

    # Refresh Access Token
    path(
        "token/refresh/",
        CookieTokenRefreshView.as_view(),
        name="token-refresh",
    ),

    # Logout
    path(
        "token/blacklist/",
        CookieTokenBlacklistView.as_view(),
        name="token-blacklist",
    ),

    # Password Reset
    path(
        "password-reset/send-otp/",
        PasswordResetSendOTPView.as_view(),
        name="password-reset-send-otp",
    ),
    path(
        "password-reset/verify-otp/",
        PasswordResetVerifyOTPView.as_view(),
        name="password-reset-verify-otp",
    ),
    path(
        "password-reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),
]
