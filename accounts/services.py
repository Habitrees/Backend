import requests
from django.conf import settings
import logging
logger = logging.getLogger(__name__)
class OTPProviderError(Exception):
    pass


def send_otp_sms(phone_e164, code):

    if not settings.OTP_PROVIDER_SEND_URL:
        raise OTPProviderError(
            "OTP URL is not configured"
        )

    if not settings.OTP_PROVIDER_TOKEN:
        raise OTPProviderError(
            "OTP token is not configured"
        )

    payload_field = settings.OTP_PROVIDER_PAYLOAD_FIELD

    if payload_field == "message":

        payload_value = settings.OTP_MESSAGE_TEMPLATE.format(
            code=code
        )

    elif payload_field == "code":

        payload_value = code

    else:

        raise OTPProviderError(
            "Invalid payload field"
        )

    body = {
        "token": settings.OTP_PROVIDER_TOKEN,

        "destination": phone_e164.lstrip("+"),

        "action": "sms",

        "payload": {
            payload_field: payload_value
        }
    }

    try:

        response = requests.post(
        settings.OTP_PROVIDER_SEND_URL,
        headers={
            "Content-Type": "application/json"
        },
        json=body,
        timeout=(
            3,
            settings.OTP_PROVIDER_TIMEOUT_SECONDS
        )
        )

        response.raise_for_status()

    except requests.HTTPError:

        logger.error("otp_provider_http_error status=%s", response.status_code)

        raise OTPProviderError(
            "Ferzz returned an HTTP error"
        ) from None
    except requests.Timeout:

        logger.error("Ferzz request timed out")

        raise OTPProviderError(
            "Ferzz timeout"
        ) from None
    except requests.ConnectionError:

        logger.error("Ferzz connection failed")

        raise OTPProviderError(
            "Ferzz connection failed"
        ) from None
    except requests.RequestException as exc:

        logger.error(
            "Ferzz request failed: %s",
            type(exc).__name__
        )

        raise OTPProviderError(
            "Ferzz request failed"
        ) from None

    return response



