
from rest_framework.throttling import AnonRateThrottle


class LoginRateThrottle(AnonRateThrottle):
    """
    Limits login attempts based on client IP.
    """
    scope = "login"


class PasswordResetSendOTPThrottle(AnonRateThrottle):
    """
    Limits password reset OTP requests based on client IP.
    """
    scope = "password_reset_send"

class PasswordResetRateThrottle(AnonRateThrottle):

    scope = "password_reset"