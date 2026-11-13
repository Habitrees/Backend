import phonenumbers

from django.conf import settings


def normalize_phone(raw_phone):

    raw_phone = str(raw_phone).strip()

    raw_phone = raw_phone.translate(
        str.maketrans(
            "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
            "01234567890123456789"
        )
    )

    if raw_phone.startswith("00"):
        raw_phone = "+" + raw_phone[2:]

    region = (
        None
        if raw_phone.startswith("+")
        else settings.DEFAULT_PHONE_REGION
    )

    try:
        phone_number = phonenumbers.parse(
            raw_phone,
            region
        )

    except phonenumbers.NumberParseException:
        raise ValueError("Invalid phone number")

    if not phonenumbers.is_valid_number(phone_number):
        raise ValueError("Invalid phone number")

    return phonenumbers.format_number(
        phone_number,
        phonenumbers.PhoneNumberFormat.E164
    )