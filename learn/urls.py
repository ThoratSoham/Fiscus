from django.urls import path

from . import views

urlpatterns = [
    path("learn/", views.lesson_list, name="lesson-list"),
    path("learn/<slug:slug>/", views.lesson_detail, name="lesson-detail"),
    path("api/lessons/attempts/", views.my_attempts, name="lesson-attempts"),
    path("api/lessons/<int:pk>/attempt/", views.submit_quiz, name="lesson-attempt"),
]
