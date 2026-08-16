from datetime import timedelta

from django.db import models
from django.utils import timezone


class Profile(models.Model):
    """Per-user streaks + badges — one int field, one boolean per badge."""

    BADGES = (
        ("badge_7_day_streak", "7-Day Streak"),
        ("badge_budget_keeper", "Budget Keeper"),
        ("badge_first_trade", "First Trade"),
        ("badge_course_complete", "Course Complete"),
    )

    user_id = models.UUIDField(unique=True, db_index=True)  # Supabase auth uid
    streak_count = models.PositiveIntegerField(default=0)
    last_activity_date = models.DateField(null=True, blank=True)

    badge_7_day_streak = models.BooleanField(default=False)
    badge_budget_keeper = models.BooleanField(default=False)
    badge_first_trade = models.BooleanField(default=False)
    badge_course_complete = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Profile {self.user_id} (streak {self.streak_count})"

    @classmethod
    def get_or_create_for(cls, user_id):
        profile, _ = cls.objects.get_or_create(user_id=user_id)
        return profile

    # ------------------------------------------------------------------
    # Streaks — activity-driven increment + daily cron reset
    # ------------------------------------------------------------------
    def record_activity(self, at=None):
        """Day-based streak: same-day no-op, next-day +1, a gap resets to 1."""
        at = at or timezone.now()
        today = timezone.localdate(at)
        if self.last_activity_date == today:
            return self.streak_count
        if self.last_activity_date == today - timedelta(days=1):
            self.streak_count += 1
        else:
            self.streak_count = 1
        self.last_activity_date = today
        self.save(update_fields=["streak_count", "last_activity_date", "updated_at"])
        return self.streak_count

    @classmethod
    def reset_stale_streaks(cls, at=None):
        """Midnight cron: zero out streaks whose last activity is a day+ old."""
        at = at or timezone.now()
        cutoff = timezone.localdate(at) - timedelta(days=1)
        return cls.objects.filter(last_activity_date__lt=cutoff, streak_count__gt=0).update(
            streak_count=0, updated_at=at
        )

    # ------------------------------------------------------------------
    # Badges — recomputed from current state; returns newly unlocked
    # ------------------------------------------------------------------
    def evaluate_badges(self):
        from learn.models import QuizAttempt
        from track.models import Budget

        newly = []

        if self.streak_count >= 7 and not self.badge_7_day_streak:
            self.badge_7_day_streak = True
            newly.append("7-Day Streak")

        if not self.badge_budget_keeper and Budget.objects.filter(user_id=self.user_id).exists():
            self.badge_budget_keeper = True
            newly.append("Budget Keeper")

        if not self.badge_first_trade and self._has_holding():
            self.badge_first_trade = True
            newly.append("First Trade")

        if not self.badge_course_complete and self._course_complete(QuizAttempt):
            self.badge_course_complete = True
            newly.append("Course Complete")

        if newly:
            self.save(update_fields=[field for field, _ in self.BADGES] + ["updated_at"])
        return newly

    def _has_holding(self):
        from invest.models import Holding

        return Holding.objects.filter(portfolio__user_id=self.user_id).exists()

    def _course_complete(self, quiz_attempt_model):
        from learn.models import Lesson

        attempted = set(
            quiz_attempt_model.objects.filter(user_id=self.user_id).values_list(
                "lesson_id", flat=True
            )
        )
        total = Lesson.objects.count()
        return total > 0 and len(attempted) >= total

    def badges_dict(self):
        return {name: bool(getattr(self, field)) for field, name in self.BADGES}
