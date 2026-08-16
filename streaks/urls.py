from django.urls import path

from . import views

urlpatterns = [
    path("api/profile/", views.profile_view, name="profile"),
    path("api/cron/streaks/", views.cron_streaks, name="cron-streaks"),
]
