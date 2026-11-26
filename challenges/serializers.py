from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from rest_framework import serializers

from .models import Challenge, ChallengeVersion, PlantSpecies, Reminder, UserPlant
from .services import normalize_nickname
from .scheduling import DEFAULT_DURATION_DAYS, MAX_DURATION_DAYS, scheduled_periods
from django.utils import timezone


class ScheduleRuleSerializer(serializers.Serializer):
    # Python weekday convention: Monday=0, Saturday=5, Sunday=6.
    weekdays = serializers.ListField(child=serializers.IntegerField(min_value=0, max_value=6), required=False, allow_empty=False)
    occurrences = serializers.IntegerField(min_value=1, required=False)

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - {'weekdays', 'occurrences'}:
            raise serializers.ValidationError('ساختار برنامه معتبر نیست.')
        return super().to_internal_value(data)


class PlantInputSerializer(serializers.Serializer):
    species = serializers.ChoiceField(choices=PlantSpecies.Code.choices)
    nickname = serializers.CharField(max_length=100)

    def validate_species(self, value):
        if PlantSpecies.objects.filter(code=value, is_active=False).exists():
            raise serializers.ValidationError('این نوع گیاه فعال نیست.')
        return value


class ReminderInputSerializer(serializers.Serializer):
    enabled = serializers.BooleanField(default=False)
    local_time = serializers.TimeField(required=False, allow_null=True)
    message = serializers.CharField(required=False, allow_blank=True, max_length=500, default='')

    def validate(self, attrs):
        if attrs['enabled'] and not attrs.get('local_time'):
            raise serializers.ValidationError({'local_time': 'زمان یادآوری را انتخاب کنید.'})
        return attrs


class ChallengeCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=150)
    description = serializers.CharField(required=False, allow_blank=True, max_length=2000, default='')
    habit_kind = serializers.ChoiceField(choices=Challenge.Kind.choices)
    start_date = serializers.DateField()
    duration_days = serializers.IntegerField(min_value=1, max_value=MAX_DURATION_DAYS, required=False, default=DEFAULT_DURATION_DAYS)
    goal_type = serializers.ChoiceField(choices=ChallengeVersion.Goal.choices)
    target_value = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True, default=None)
    unit = serializers.CharField(max_length=32, required=False, allow_null=True, default=None)
    period_type = serializers.ChoiceField(choices=ChallengeVersion.Period.choices)
    schedule_rule = ScheduleRuleSerializer()
    streak_policy = serializers.ChoiceField(choices=ChallengeVersion.Policy.choices)
    plant = PlantInputSerializer()
    reminder = ReminderInputSerializer(required=False)

    def validate(self, attrs):
        user = self.context['request'].user
        existing = self.context.get('challenge')
        try:
            zone = ZoneInfo(existing.versions.order_by('-version_no').first().timezone if existing else user.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise serializers.ValidationError({'timezone': 'منطقه زمانی حساب معتبر نیست.'})
        if not existing and attrs['start_date'] < timezone.localdate(timezone=zone):
            raise serializers.ValidationError({'start_date': 'تاریخ شروع نباید در گذشته باشد.'})
        if not existing and (attrs['start_date'] - timezone.localdate(timezone=zone)).days > 730:
            raise serializers.ValidationError({'start_date': 'تاریخ شروع بیش از حد دور است.'})
        if attrs['streak_policy'] == 'flexible' and attrs['period_type'] != 'daily':
            raise serializers.ValidationError({'streak_policy':'حالت انعطاف‌پذیر فعلاً فقط برای برنامه روزانه است.'})
        binary = attrs['goal_type'] == 'binary'
        positive = attrs['habit_kind'] == 'positive'
        if binary:
            if attrs['target_value'] is not None or attrs['unit'] is not None:
                raise serializers.ValidationError('هدف انجام/عدم انجام مقدار و واحد عددی ندارد.')
            attrs['comparison'] = 'eq'
            # True means the behavior occurred, not that the goal succeeded.
            attrs['binary_success'] = positive
        else:
            value = attrs['target_value']
            if value is None or value < 0 or (positive and value == 0):
                raise serializers.ValidationError({'target_value': 'مقدار هدف معتبر نیست.'})
            if not attrs['unit']:
                raise serializers.ValidationError({'unit': 'واحد هدف الزامی است.'})
            attrs['comparison'] = 'gte' if positive else 'lte'
            attrs['binary_success'] = None
        rule = attrs['schedule_rule']
        if attrs['period_type'] == 'daily':
            days = rule.get('weekdays', [])
            if not days or len(days) != len(set(days)) or 'occurrences' in rule:
                raise serializers.ValidationError({'schedule_rule': 'روزهای هفته را بدون تکرار انتخاب کنید.'})
            rule['weekdays'] = sorted(days)
        elif 'occurrences' not in rule or 'weekdays' in rule:
            raise serializers.ValidationError({'schedule_rule': 'تعداد نوبت در بازه را مشخص کنید.'})
        if attrs['period_type'] != 'daily' and rule['occurrences'] > (7 if attrs['period_type'] == 'weekly' else 31):
            raise serializers.ValidationError({'schedule_rule': 'تعداد نوبت بیشتر از ظرفیت بازه است.'})
        if not list(scheduled_periods(attrs['start_date'], attrs['duration_days'], attrs['period_type'], rule)):
            raise serializers.ValidationError({'schedule_rule':'در مدت تعیین‌شده هیچ نوبتی وجود ندارد.'})
        name = normalize_nickname(attrs['plant']['nickname'])
        names = UserPlant.objects.filter(owner_user=user, normalized_nickname=name)
        if existing:
            names = names.exclude(participation__challenge=existing)
        if names.exists():
            raise serializers.ValidationError({'plant': {'nickname': 'این نام گیاه قبلاً انتخاب شده است.'}})
        return attrs


class UserPlantSerializer(serializers.ModelSerializer):
    species = serializers.CharField(source="species.code", read_only=True)

    class Meta:
        model = UserPlant
        fields = ['id','nickname','species']


class ReminderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reminder
        fields = ['id','enabled','local_time','timezone','message']


class VersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChallengeVersion
        fields = ['version_no','goal_type','unit','target_value','comparison','binary_success',
                  'period_type','schedule_rule','start_date','duration_days','timezone','streak_policy']


class ChallengeReadSerializer(serializers.ModelSerializer):
    version = serializers.SerializerMethodField()
    participation_id = serializers.SerializerMethodField()
    participation_status = serializers.SerializerMethodField()
    plant = serializers.SerializerMethodField()
    reminders = serializers.SerializerMethodField()
    progress_percentage = serializers.IntegerField(source='stats.progress_percentage', read_only=True)
    completed_periods = serializers.IntegerField(source='stats.completed_periods', read_only=True)
    total_periods = serializers.IntegerField(source='stats.total_periods', read_only=True)
    current_streak = serializers.IntegerField(source='stats.current_streak', read_only=True)
    best_streak = serializers.IntegerField(source='stats.best_streak', read_only=True)
    streak_unit = serializers.CharField(source='stats.streak_unit', read_only=True)
    local_date = serializers.DateField(source='stats.local_date', read_only=True)
    due_today = serializers.BooleanField(source='stats.due_today', read_only=True)
    done_today = serializers.BooleanField(source='stats.done_today', read_only=True)
    today_log = serializers.JSONField(source='stats.today_log', read_only=True, allow_null=True)
    habit_status = serializers.CharField(source='stats.habit_status', read_only=True)

    def get_version(self, obj):
        return VersionSerializer(obj.current_versions[0]).data

    def get_participation_id(self, obj):
        return obj.own_participations[0].pk

    def get_participation_status(self, obj):
        return 'completed' if obj.stats['habit_status'] == 'completed' else obj.own_participations[0].status

    def get_plant(self, obj):
        return UserPlantSerializer(obj.own_participations[0].plant).data

    def get_reminders(self, obj):
        return ReminderSerializer(obj.own_participations[0].reminders.all(), many=True).data

    class Meta:
        model = Challenge
        fields = ['id','title','description','habit_kind','visibility','status','created_at',
                  'version','participation_id','participation_status','plant','reminders',
                  'progress_percentage','completed_periods','total_periods','current_streak','best_streak',
                  'streak_unit','local_date','due_today','done_today','today_log','habit_status']


class LogInputSerializer(serializers.Serializer):
    numeric_value = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0, required=False, allow_null=True)
    binary_value = serializers.BooleanField(required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, max_length=500, default='')


class TabCountsSerializer(serializers.Serializer):
    all = serializers.IntegerField()
    today = serializers.IntegerField()
    completed = serializers.IntegerField()


class ChallengeListSerializer(serializers.Serializer):
    counts = TabCountsSerializer()
    results = ChallengeReadSerializer(many=True)
