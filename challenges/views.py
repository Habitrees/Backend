from datetime import date
from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Challenge, ChallengeVersion, Participation, HabitPeriod, UserPlant
from .serializers import ChallengeCreateSerializer, ChallengeReadSerializer, ChallengeListSerializer, LogInputSerializer
from .services import create_personal_challenge, edit_personal_challenge, normalize_nickname, metrics, set_log


def owned_challenges(user):
    return Challenge.objects.filter(created_by=user, visibility='personal', status='active', participations__user=user)


def read_queryset(user):
    return owned_challenges(user).prefetch_related(
        Prefetch('versions', queryset=ChallengeVersion.objects.order_by('-version_no'), to_attr='current_versions'),
        Prefetch('participations', queryset=Participation.objects.filter(user=user).select_related('plant__species').prefetch_related(
            'reminders', Prefetch('periods',queryset=HabitPeriod.objects.select_related('version').prefetch_related('logs').order_by('starts_at'))), to_attr='own_participations'))


def load(user, pk):
    obj = get_object_or_404(read_queryset(user),pk=pk)
    obj.stats = metrics(obj)
    return obj


def representation(user, pk):
    return ChallengeReadSerializer(load(user,pk)).data


def validate_input(serializer_class, data, request, **extra):
    if not isinstance(data,dict):
        raise serializers.ValidationError('بدنه باید یک JSON object باشد.')
    serializer = serializer_class(data=data,context={'request':request,**extra})
    if set(data) - set(serializer.fields):
        raise serializers.ValidationError({'detail':'فیلد ناشناخته در درخواست وجود دارد.'})
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def nickname_conflict(user, plant, exclude=None):
    qs=UserPlant.objects.filter(owner_user=user,normalized_nickname=normalize_nickname(plant['nickname']))
    if exclude is not None:
        qs=qs.exclude(participation__challenge_id=exclude)
    if qs.exists():
        raise serializers.ValidationError({'plant':{'nickname':'این نام گیاه قبلاً انتخاب شده است.'}})


class ChallengeListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Challenges'], responses=ChallengeListSerializer, parameters=[
        OpenApiParameter('filter',str,enum=['all','today','completed']),
        OpenApiParameter('ordering',str,enum=['newest','oldest','progress','streak'])])
    def get(self,request):
        selected=request.query_params.get('filter','all')
        ordering=request.query_params.get('ordering','newest')
        if selected not in ('all','today','completed'):
            raise serializers.ValidationError({'filter':'فیلتر معتبر نیست.'})
        if ordering not in ('newest','oldest','progress','streak'):
            raise serializers.ValidationError({'ordering':'مرتب‌سازی معتبر نیست.'})
        order=('created_at','pk') if ordering=='oldest' else ('-created_at','-pk')
        items=list(read_queryset(request.user).order_by(*order))
        now=timezone.now()
        for obj in items:
            obj.stats=metrics(obj,now=now)
        today=[obj for obj in items if obj.stats['due_today'] and (obj.stats['habit_status'] != 'completed' or obj.stats['done_today'])]
        completed=[obj for obj in items if obj.stats['habit_status']=='completed']
        groups={'all':items,'today':today,'completed':completed}
        result=groups[selected]
        if ordering in ('progress','streak'):
            key='progress_percentage' if ordering=='progress' else 'current_streak'
            result=sorted(result,key=lambda obj:obj.stats[key],reverse=True)
        return Response({'counts':{key:len(value) for key,value in groups.items()},'results':ChallengeReadSerializer(result,many=True).data})

    @extend_schema(tags=['Challenges'],request=ChallengeCreateSerializer,responses={201:ChallengeReadSerializer})
    def post(self,request):
        data=validate_input(ChallengeCreateSerializer,request.data,request)
        try:
            obj=create_personal_challenge(user=request.user,data=data)
        except IntegrityError:
            nickname_conflict(request.user,data['plant'])
            raise
        return Response(representation(request.user,obj.pk),status=status.HTTP_201_CREATED)


def merge_patch(obj, incoming):
    if not isinstance(incoming,dict):
        raise serializers.ValidationError('بدنه باید JSON object باشد.')
    version=obj.current_versions[0]
    p=obj.own_participations[0]
    reminder=next(iter(p.reminders.all()),None)
    merged={key:getattr(obj,key) for key in ('title','description','habit_kind')}
    merged.update({key:getattr(version,key) for key in ('start_date','duration_days','goal_type','target_value','unit','period_type','schedule_rule','streak_policy')})
    merged['plant']={'species':p.plant.species.code,'nickname':p.plant.nickname}
    merged['reminder']={'enabled':reminder.enabled,'local_time':reminder.local_time,'message':reminder.message} if reminder else {'enabled':False}
    for key,val in incoming.items():
        if key not in merged:
            raise serializers.ValidationError({key:'این فیلد قابل ویرایش نیست.'})
        if key in ('plant','reminder') and isinstance(val,dict):
            merged[key]={**merged[key],**val}
        else:
            merged[key]=val
    if incoming.get('goal_type')=='binary' and version.goal_type!='binary':
        for key in ('target_value','unit'):
            if key not in incoming:
                merged[key]=None
    return merged


class ChallengeDetailView(APIView):
    permission_classes=[IsAuthenticated]

    @extend_schema(tags=['Challenges'],responses=ChallengeReadSerializer)
    def get(self,request,pk):
        return Response(representation(request.user,pk))

    @extend_schema(tags=['Challenges'],request=ChallengeCreateSerializer(partial=True),responses=ChallengeReadSerializer)
    def patch(self,request,pk):
        try:
            with transaction.atomic():
                locked=get_object_or_404(owned_challenges(request.user).select_for_update(of=('self',)),pk=pk)
                obj=load(request.user,pk)
                data=validate_input(ChallengeCreateSerializer,merge_patch(obj,request.data),request,challenge=locked)
                edit_personal_challenge(locked,data)
        except IntegrityError:
            nickname_conflict(request.user,data['plant'],exclude=pk)
            raise
        return Response(representation(request.user,pk))

    @extend_schema(tags=['Challenges'],request=None,responses={204:None})
    def delete(self,request,pk):
        with transaction.atomic():
            obj=get_object_or_404(owned_challenges(request.user).select_for_update(of=('self',)),pk=pk)
            # Archive to preserve history; no longer visible in personal lists.
            obj.status='archived'
            obj.save(update_fields=['status'])
            obj.participations.filter(user=request.user).update(status='archived')
            from .models import Reminder
            Reminder.objects.filter(participation__challenge=obj).update(enabled=False)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ChallengeLogView(APIView):
    permission_classes=[IsAuthenticated]

    def parse_day(self,value):
        try:
            parsed=date.fromisoformat(value)
            if parsed.isoformat()!=value:
                raise ValueError
            return parsed
        except ValueError:
            raise serializers.ValidationError({'date':'فرمت تاریخ YYYY-MM-DD است.'})

    @extend_schema(tags=['Challenges'],request=LogInputSerializer,responses=ChallengeReadSerializer)
    def put(self,request,pk,day):
        day=self.parse_day(day)
        with transaction.atomic():
            obj=get_object_or_404(owned_challenges(request.user).select_for_update(of=('self',)),pk=pk)
            data=validate_input(LogInputSerializer,request.data,request)
            set_log(obj,day,data)
        return Response(representation(request.user,pk))

    @extend_schema(tags=['Challenges'],request=None,responses=ChallengeReadSerializer)
    def delete(self,request,pk,day):
        day=self.parse_day(day)
        with transaction.atomic():
            obj=get_object_or_404(owned_challenges(request.user).select_for_update(of=('self',)),pk=pk)
            set_log(obj,day)
        return Response(representation(request.user,pk))
