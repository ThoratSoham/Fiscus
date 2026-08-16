from django.db import models
from django.utils import timezone


def validate_quiz_questions(quiz_questions):
    """Structural check: a dict with a non-empty list of question objects."""
    questions = quiz_questions.get("questions") if isinstance(quiz_questions, dict) else None
    if not isinstance(questions, list) or not questions:
        return False
    for q in questions:
        if not isinstance(q, dict):
            return False
        options = q.get("options")
        if not q.get("question") or not isinstance(options, list) or len(options) < 2:
            return False
        correct = q.get("correct")
        if not isinstance(correct, int) or not (0 <= correct < len(options)):
            return False
    return True


class Lesson(models.Model):
    """A lesson with static content and an embedded 3-question quiz."""

    title = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)
    summary = models.CharField(max_length=255, blank=True, default="")
    content = models.TextField(help_text="HTML — static lesson content, DB-stored, no CMS.")
    quiz_questions = models.JSONField(
        help_text='{"questions": [{"question": str, "options": [str], "correct": int}]}'
    )
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.title


class QuizAttempt(models.Model):
    """A user's quiz completion. streak_count feeds Phase 5 badge logic."""

    user_id = models.UUIDField(db_index=True)  # Supabase auth uid
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="attempts")
    score = models.PositiveIntegerField()  # 0-100
    streak_count = models.PositiveIntegerField(default=0)
    badge = models.CharField(max_length=64, blank=True, default="")  # reserved for Phase 5
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.lesson}: {self.score}% (streak {self.streak_count})"

    @classmethod
    def record_attempt(cls, user_id, lesson, score, at=None):
        """Create an attempt; the day-based streak comes from the Profile."""
        from streaks.models import Profile

        at = at or timezone.now()
        profile = Profile.get_or_create_for(user_id)
        streak = profile.record_activity(at=at)
        cls.objects.create(
            user_id=user_id, lesson=lesson, score=score, streak_count=streak
        )
        return streak
