from django.urls import path

from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    RegisterSendOTPView,
    RegisterVerifyOTPView,
    LoginView,
    PasswordResetSendOTPView,
    )
from rest_framework_simplejwt.views import (
    TokenRefreshView,
    TokenBlacklistView,
)

urlpatterns = [

    path(
        "register/send-otp/",
        RegisterSendOTPView.as_view(),
        name="register-send-otp"
    ),

    path(
        "register/verify-otp/",
        RegisterVerifyOTPView.as_view(),
        name="register-verify-otp"
    ),

    path(
        "token/refresh/",
        TokenRefreshView.as_view(),
        name="token-refresh"
    ),
    path(
    "token/blacklist/",
    TokenBlacklistView.as_view(),
    name="token-blacklist"
    ),
    path(
    "login/",
    LoginView.as_view(),
    name="login",
    ),

    path(
        "password-reset/send-otp/",
        PasswordResetSendOTPView.as_view(),
        name="password-reset-send-otp",
    ),

]