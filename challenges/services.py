import unicodedata
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from .models import Challenge, ChallengeVersion, Participation, PlantSpecies, Reminder, UserPlant, HabitPeriod, HabitLog
from .scheduling import scheduled_periods, successful, streak


def normalize_nickname(value):
    value = unicodedata.normalize('NFKC', value).translate(str.maketrans({'ي':'ی','ك':'ک'}))
    return ' '.join(value.split()).casefold()


def day_start(day, zone):
    return datetime.combine(day, time.min, tzinfo=zone)


def generate_periods(participation, version):
    zone = ZoneInfo(version.timezone)
    HabitPeriod.objects.bulk_create([
        HabitPeriod(participation=participation, version=version,
                    starts_at=day_start(start,zone), ends_at=day_start(end+timedelta(days=1),zone))
        for start,end,_ in scheduled_periods(version.start_date, version.duration_days, version.period_type, version.schedule_rule)
    ])


def save_plant(participation, plant):
    species, _ = PlantSpecies.objects.get_or_create(code=plant['species'], defaults={'name':PlantSpecies.Code(plant['species']).label})
    if not species.is_active:
        raise ValidationError({'plant': 'این نوع گیاه فعال نیست.'})
    UserPlant.objects.update_or_create(participation=participation, defaults={
        'owner_user':participation.user, 'species':species, 'nickname':plant['nickname'],
        'normalized_nickname':normalize_nickname(plant['nickname'])})


def save_reminder(participation, reminder, zone):
    participation.reminders.all().delete()
    if reminder and reminder.get('local_time') is not None:
        Reminder.objects.create(participation=participation, timezone=zone, **reminder)


@transaction.atomic
def create_personal_challenge(*, user, data):
    data = dict(data)
    plant = data.pop('plant')
    reminder = data.pop('reminder', None)
    challenge = Challenge.objects.create(created_by=user, visibility='personal', title=data.pop('title'), description=data.pop('description',''), habit_kind=data.pop('habit_kind'))
    version = ChallengeVersion.objects.create(challenge=challenge, timezone=user.timezone, **data)
    participation = Participation.objects.create(user=user, challenge=challenge)
    generate_periods(participation, version)
    save_plant(participation, plant)
    save_reminder(participation, reminder, version.timezone)
    return challenge


def current_version(challenge):
    return challenge.versions.order_by('-version_no').first()


def local_today(version):
    return timezone.localdate(timezone=ZoneInfo(version.timezone))


def period_dates(period):
    zone = ZoneInfo(period.version.timezone)
    return period.starts_at.astimezone(zone).date(), period.ends_at.astimezone(zone).date() - timedelta(days=1)


def period_outcome(period, today):
    start,end = period_dates(period)
    v = period.version
    quota = 1 if v.period_type == 'daily' else min(v.schedule_rule['occurrences'],(end-start).days+1)
    logs = list(period.logs.all())
    count = sum(successful(v,log) for log in logs if log.local_date <= today)
    return start,end,count >= quota,logs


def metrics(challenge, *, now=None):
    p = challenge.own_participations[0]
    version = challenge.current_versions[0]
    today = (now or timezone.now()).astimezone(ZoneInfo(version.timezone)).date()
    rows = []
    done_today = False
    due_today = False
    today_log = None
    for period in p.periods.all():
        start,end,ok,logs = period_outcome(period,today)
        rows.append((start,end,ok,period.version.streak_policy,period.version.period_type))
        if start <= today <= end:
            due_today = True
            log = next((x for x in logs if x.local_date == today),None)
            if log:
                done_today = successful(period.version,log)
                today_log = {'numeric_value':str(log.numeric_delta) if log.numeric_delta is not None else None,'binary_value':log.binary_value,'note':log.note}
    completed = sum(ok for _,_,ok,_,_ in rows)
    total = len(rows)
    current,best = streak(rows,today)
    end_date = version.start_date + timedelta(days=version.duration_days-1)
    state = 'completed' if total and completed == total else ('upcoming' if today < version.start_date else ('expired' if today > end_date else 'active'))
    return dict(progress_percentage=(100 if total and completed==total else min(99,(200*completed+total)//(2*total)) if total else 0), completed_periods=completed,total_periods=total,current_streak=current,best_streak=best,streak_unit=version.period_type, local_date=today.isoformat(),due_today=due_today,done_today=done_today,today_log=today_log,habit_status=state)


def set_log(challenge, day, data=None):
    """Called under a locked Challenge transaction. PUT replaces, DELETE removes."""
    v = current_version(challenge)
    today = local_today(v)
    if day != today:
        raise ValidationError({'date':'فعلاً فقط ثبت یا لغو عملکرد امروز مجاز است.'})
    p = challenge.participations.get(user=challenge.created_by)
    zone = ZoneInfo(v.timezone)
    boundary = day_start(day,zone)
    period = p.periods.filter(starts_at__lte=boundary,ends_at__gt=boundary).select_related('version').first()
    if not period:
        raise ValidationError({'date':'این روز در برنامه عادت نیست.'})
    if data is None:
        period.logs.filter(local_date=day).delete()
    else:
        value,binary = data.get('numeric_value'),data.get('binary_value')
        if period.version.goal_type == 'binary':
            if binary is None or value is not None:
                raise ValidationError({'binary_value':'فقط مقدار true یا false ارسال کنید.'})
        elif value is None or binary is not None:
            raise ValidationError({'numeric_value':'فقط مقدار عددی غیرمنفی ارسال کنید.'})
        HabitLog.objects.update_or_create(period=period,local_date=day,defaults={'numeric_delta':value,'binary_value':binary,'note':data.get('note','')})
    _,_,ok,_ = period_outcome(period,today)
    period.result = 'success' if ok else 'pending'
    period.save(update_fields=['result'])
    # Keep completed status synchronized on writes; read status is derived.
    all_ok = all(period_outcome(x,today)[2] for x in p.periods.select_related('version').prefetch_related('logs'))
    p.status = 'completed' if all_ok else 'active'
    p.completed_at = (p.completed_at or timezone.now()) if all_ok else None
    p.save(update_fields=['status','completed_at'])


def edit_personal_challenge(challenge, data):
    """Caller validates merged data and locks Challenge. Preserve recorded history."""
    data = dict(data)
    p = challenge.participations.get(user=challenge.created_by)
    v = current_version(challenge)
    plant = data.pop('plant')
    reminder = data.pop('reminder',None)
    title = data.pop('title'); description = data.pop('description'); kind = data.pop('habit_kind')
    changed = kind != challenge.habit_kind or any(getattr(v,k) != val for k,val in data.items())
    if changed:
        today = local_today(v)
        if today > v.start_date or p.periods.filter(logs__isnull=False).exists():
            raise ValidationError({'detail':'تغییر هدف، نوع، برنامه یا قانون بعد از شروع تاریخچه فعلاً مجاز نیست.'})
        if data['start_date'] < today or (data['start_date']-today).days > 730:
            raise ValidationError({'start_date':'تاریخ شروع معتبر نیست.'})
        p.periods.all().delete()
        v = ChallengeVersion.objects.create(challenge=challenge,version_no=v.version_no+1,timezone=v.timezone,**data)
        generate_periods(p,v)
    challenge.title=title; challenge.description=description; challenge.habit_kind=kind
    challenge.save(update_fields=['title','description','habit_kind'])
    save_plant(p,plant)
    save_reminder(p,reminder,v.timezone)
