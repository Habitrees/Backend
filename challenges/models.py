import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class Challenge(models.Model):
    class Kind(models.TextChoices):
        POSITIVE = 'positive', 'Positive'
        NEGATIVE = 'negative', 'Negative'

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                   related_name='created_challenges')
    title = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    habit_kind = models.CharField(max_length=12, choices=Kind.choices)
    visibility = models.CharField(max_length=16, default='personal', choices=[('personal', 'Personal')])
    status = models.CharField(max_length=16, default='active', choices=[('active', 'Active'), ('archived', 'Archived')])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'challenges'
        indexes = [models.Index(fields=['created_by', 'created_at'])]


class ChallengeVersion(models.Model):
    class Goal(models.TextChoices):
        TIME = 'time', 'Time'
        COUNT = 'count', 'Count'
        BINARY = 'binary', 'Binary'

    class Period(models.TextChoices):
        DAILY = 'daily', 'Daily'
        WEEKLY = 'weekly', 'Weekly'
        MONTHLY = 'monthly', 'Monthly'

    class Policy(models.TextChoices):
        STRICT = 'strict', 'Strict'
        FLEXIBLE = 'flexible', 'Flexible'

    challenge = models.ForeignKey(Challenge, on_delete=models.CASCADE, related_name='versions')
    version_no = models.PositiveIntegerField(default=1)
    effective_from = models.DateTimeField(default=timezone.now)
    goal_type = models.CharField(max_length=10, choices=Goal.choices)
    unit = models.CharField(max_length=32, null=True, blank=True)
    target_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    comparison = models.CharField(max_length=3, choices=[('gte', 'At least'), ('lte', 'At most'), ('eq', 'Equal')])
    binary_success = models.BooleanField(null=True, blank=True)
    period_type = models.CharField(max_length=10, choices=Period.choices)
    schedule_rule = models.JSONField(default=dict)
    start_date = models.DateField()
    duration_days = models.PositiveIntegerField(null=True, blank=True)
    timezone = models.CharField(max_length=64)
    streak_policy = models.CharField(max_length=12, choices=Policy.choices)
    policy_config = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'challenge_versions'
        constraints = [
            models.UniqueConstraint(fields=['challenge', 'version_no'], name='unique_challenge_version'),
            models.CheckConstraint(condition=models.Q(duration_days__isnull=True) | models.Q(duration_days__gt=0), name='positive_challenge_duration'),
            models.CheckConstraint(condition=(models.Q(goal_type='binary', target_value__isnull=True, unit__isnull=True, binary_success__isnull=False, comparison='eq') | models.Q(goal_type__in=['time','count'], target_value__isnull=False, unit__isnull=False, binary_success__isnull=True, comparison__in=['gte','lte'])), name='valid_challenge_goal_shape'),
            models.CheckConstraint(condition=models.Q(target_value__isnull=True) | models.Q(target_value__gt=0) | models.Q(target_value=0, comparison='lte'), name='valid_challenge_target'),
        ]


class Participation(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='habit_participations')
    challenge = models.ForeignKey(Challenge, on_delete=models.CASCADE, related_name='participations')
    joined_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=16, default='active', choices=[('active','Active'), ('completed','Completed'), ('archived','Archived')])
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'participations'
        constraints = [models.UniqueConstraint(fields=['user','challenge'], name='unique_challenge_participant')]


class PlantSpecies(models.Model):
    class Code(models.TextChoices):
        POTHOS = 'pothos', 'پتوس'
        SANSEVIERIA = 'sansevieria', 'سانسوریا'
        ORCHID = 'orchid', 'ارکیده'

    code = models.CharField(max_length=32, choices=Code.choices, unique=True)
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'plant_species'


class UserPlant(models.Model):
    participation = models.OneToOneField(Participation, on_delete=models.CASCADE, related_name='plant')
    owner_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='habit_plants')
    species = models.ForeignKey(PlantSpecies, on_delete=models.PROTECT, related_name='user_plants')
    nickname = models.CharField(max_length=100)
    normalized_nickname = models.CharField(max_length=200, editable=False)
    planted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'user_plants'
        constraints = [models.UniqueConstraint(fields=['owner_user','normalized_nickname'], name='unique_owner_plant_nickname')]


class Reminder(models.Model):
    participation = models.ForeignKey(Participation, on_delete=models.CASCADE, related_name='reminders')
    local_time = models.TimeField()
    timezone = models.CharField(max_length=64)
    message = models.TextField(blank=True)
    enabled = models.BooleanField(default=True)

    class Meta:
        db_table = 'reminders'
        constraints = [models.UniqueConstraint(fields=['participation','local_time'], name='unique_participation_reminder_time')]


class HabitPeriod(models.Model):
    participation = models.ForeignKey(Participation, on_delete=models.CASCADE, related_name='periods')
    version = models.ForeignKey(ChallengeVersion, on_delete=models.CASCADE, related_name='periods')
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()  # exclusive
    result = models.CharField(max_length=12, default='pending', choices=[('pending','Pending'),('success','Success'),('failure','Failure')])
    finalized_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'habit_periods'
        ordering = ['starts_at']
        constraints = [
            models.UniqueConstraint(fields=['participation','starts_at'], name='unique_participation_period'),
            models.CheckConstraint(condition=models.Q(ends_at__gt=models.F('starts_at')), name='valid_habit_period_bounds'),
        ]


class HabitLog(models.Model):
    """One daily absolute measurement per period (MVP extension to ERD)."""
    period = models.ForeignKey(HabitPeriod, on_delete=models.CASCADE, related_name='logs')
    local_date = models.DateField()
    numeric_delta = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    binary_value = models.BooleanField(null=True, blank=True)
    note = models.TextField(blank=True)
    recorded_at = models.DateTimeField(auto_now=True)
    idempotency_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    class Meta:
        db_table = 'habit_logs'
        constraints = [
            models.UniqueConstraint(fields=['period','local_date'], name='unique_period_daily_log'),
            models.CheckConstraint(condition=(models.Q(numeric_delta__isnull=False,binary_value__isnull=True,numeric_delta__gte=0) | models.Q(numeric_delta__isnull=True,binary_value__isnull=False)), name='valid_habit_log_value'),
        ]
