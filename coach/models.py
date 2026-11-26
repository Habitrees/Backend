from django.conf import settings
from django.db import models


class AIConversation(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)


class AIMessage(models.Model):
    conversation = models.ForeignKey(AIConversation, related_name="messages", on_delete=models.CASCADE)
    text = models.TextField()
    reply_to = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="response",
    )
    created_at = models.DateTimeField(auto_now_add=True)


class AIProposal(models.Model):
    class Decision(models.TextChoices):
        PENDING = "pending"
        ACCEPTED = "accepted"
        REJECTED = "rejected"
    class Action(models.TextChoices):
        CREATE = "create_challenge", "Create Challenge"
        UPDATE = "update_challenge", "Update Challenge"

    action = models.CharField(
        max_length=20,
        choices=Action.choices,
        default=Action.UPDATE,
    )

    result_challenge = models.ForeignKey(
        "challenges.Challenge",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="applied_ai_proposals",
    )
    message = models.OneToOneField(AIMessage, related_name="proposal", on_delete=models.CASCADE)
    challenge = models.ForeignKey(
        "challenges.Challenge", null=True, on_delete=models.SET_NULL,
    )
    changes = models.JSONField()
    expires_at = models.DateTimeField()
    decision = models.CharField(max_length=8, choices=Decision.choices, default=Decision.PENDING)
    decided_at = models.DateTimeField(null=True)
