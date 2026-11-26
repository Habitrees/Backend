from datetime import timedelta
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken
from .models import Challenge, Participation, PlantSpecies, UserPlant, HabitLog, HabitPeriod


class ChallengeAPITests(APITestCase):
    def setUp(self):
        def make_user(phone, username):
            return get_user_model().objects.create_user(phone=phone,username=username,full_name=username,
                password='Strong-Example-123',terms_version='test',terms_accepted_at=timezone.now(),phone_verified_at=timezone.now())
        self.user=make_user('+989120000001','first')
        self.other=make_user('+989120000002','second')
        self.url=reverse('challenges:list-create')
        self.today=timezone.localdate().isoformat()
        self.payload={'title':'مطالعه','habit_kind':'positive','start_date':self.today,'duration_days':2,
            'goal_type':'time','target_value':'20','unit':'minute','period_type':'daily','schedule_rule':{'weekdays':list(range(7))},
            'streak_policy':'strict','plant':{'species':'pothos','nickname':'برگ آرامش'}}
        self.client.force_authenticate(self.user)

    def create(self):
        r=self.client.post(self.url,self.payload,format='json')
        self.assertEqual(r.status_code,201,r.data)
        return r.data['id']

    def detail(self,pk):
        return reverse('challenges:detail',args=[pk])

    def log(self,pk):
        return reverse('challenges:log',args=[pk,self.today])

    def test_authentication_and_jwt(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url).status_code,401)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer '+str(RefreshToken.for_user(self.user).access_token))
        self.assertEqual(self.client.get(self.url).status_code,200)

    def test_create_and_isolation(self):
        pk=self.create()
        self.assertEqual(Participation.objects.get().user,self.user)
        self.assertEqual(HabitPeriod.objects.count(),2)
        self.assertEqual(UserPlant.objects.get().owner_user,self.user)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(self.url).data['results'],[])
        for r in (self.client.get(self.detail(pk)),self.client.patch(self.detail(pk),{'title':'other'},format='json'),self.client.delete(self.detail(pk)),self.client.put(self.log(pk),{'numeric_value':20},format='json'),self.client.delete(self.log(pk))):
            self.assertEqual(r.status_code,404,r.data)

    def test_invalid_schedule_and_plant(self):
        self.payload['schedule_rule']={'weekdays':[1,1]}
        self.assertEqual(self.client.post(self.url,self.payload,format='json').status_code,400)
        self.payload['schedule_rule']={'weekdays':list(range(7))}
        self.payload['plant']['species']='unknown'
        self.assertEqual(self.client.post(self.url,self.payload,format='json').status_code,400)
        self.assertFalse(Challenge.objects.exists())

    def test_progress_retry_undo_and_filters(self):
        self.payload['duration_days']=1
        pk=self.create()
        before=self.client.get(self.url+'?filter=today').data
        self.assertEqual(before['counts'],{'all':1,'today':1,'completed':0})
        self.assertEqual(before['results'][0]['progress_percentage'],0)
        for _ in range(2):
            r=self.client.put(self.log(pk),{'numeric_value':'20'},format='json')
            self.assertEqual(r.status_code,200,r.data)
            self.assertEqual(r.data['progress_percentage'],100)
            self.assertEqual(r.data['current_streak'],1)
        self.assertEqual(HabitLog.objects.count(),1)
        self.assertEqual(self.client.get(self.url+'?filter=completed').data['counts']['completed'],1)
        r=self.client.delete(self.log(pk))
        self.assertEqual(r.status_code,200,r.data)
        self.assertEqual(r.data['progress_percentage'],0)
        self.assertFalse(r.data['done_today'])
        self.assertEqual(HabitLog.objects.count(),0)

    def test_patch_and_archive(self):
        pk=self.create()
        r=self.client.patch(self.detail(pk),{'target_value':'30','plant':{'nickname':'برگ نو'}},format='json')
        self.assertEqual(r.status_code,200,r.data)
        self.assertEqual(r.data['version']['version_no'],2)
        self.assertEqual(r.data['plant']['nickname'],'برگ نو')
        self.assertEqual(self.client.put(self.log(pk),{'numeric_value':30},format='json').status_code,200)
        self.assertEqual(self.client.patch(self.detail(pk),{'target_value':'50'},format='json').status_code,400)
        self.assertEqual(self.client.patch(self.detail(pk),{'title':'جدید'},format='json').status_code,200)
        self.assertEqual(self.client.delete(self.detail(pk)).status_code,204)
        self.assertEqual(self.client.get(self.detail(pk)).status_code,404)
        self.assertEqual(HabitLog.objects.count(),1)

    def test_negative_binary(self):
        self.payload.update(habit_kind='negative',goal_type='binary',target_value=None,unit=None)
        pk=self.create()
        r=self.client.put(self.log(pk),{'binary_value':False},format='json')
        self.assertEqual(r.status_code,200,r.data)
        self.assertTrue(r.data['done_today'])
        self.assertEqual(r.data['progress_percentage'],50)

    def test_species_and_duplicate_nickname(self):
        self.create()
        self.assertEqual(self.client.post(self.url,self.payload,format='json').status_code,400)
        self.payload['plant']['nickname']='دوم'
        self.create()
        self.assertEqual(PlantSpecies.objects.count(),1)
        self.assertEqual(self.client.get(self.url+'plant-species/').status_code,404)

    def test_future_and_unscheduled_log_rejected(self):
        self.payload['start_date']=(timezone.localdate()+timedelta(days=1)).isoformat()
        pk=self.create()
        self.assertEqual(self.client.put(self.log(pk),{'numeric_value':20},format='json').status_code,400)
