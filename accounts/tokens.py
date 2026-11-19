
from rest_framework_simplejwt.tokens import RefreshToken


class HabitreeRefreshToken(RefreshToken):

    # Do not copy remember_me into the Access Token.
    no_copy_claims = (
        RefreshToken.no_copy_claims + ("remember_me",)
    )
