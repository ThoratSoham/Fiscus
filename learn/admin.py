from django.contrib import admin

from .models import Lesson, QuizAttempt


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ("order", "title", "slug")
    prepopulated_fields = {"slug": ("title",)}
    search_fields = ("title",)


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = ("lesson", "score", "streak_count", "badge", "created_at", "user_id")
    list_filter = ("lesson", "created_at")
    search_fields = ("user_id",)
