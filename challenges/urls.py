from django.urls import path
from .views import ChallengeListCreateView, ChallengeDetailView, ChallengeLogView

app_name = 'challenges'
urlpatterns = [
    path('', ChallengeListCreateView.as_view(), name='list-create'),
    path('<int:pk>/', ChallengeDetailView.as_view(), name='detail'),
    path('<int:pk>/logs/<str:day>/', ChallengeLogView.as_view(), name='log'),
]
