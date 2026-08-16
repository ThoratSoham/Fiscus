from django.contrib import admin

from .models import Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user_id", "streak_count", "last_activity_date", "badge_7_day_streak",
                    "badge_budget_keeper", "badge_first_trade", "badge_course_complete")
    search_fields = ("user_id",)
