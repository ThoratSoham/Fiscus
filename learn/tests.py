import datetime
import uuid
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from core.auth import SupabaseUser
from .models import Lesson, QuizAttempt


def make_lesson(title="Test Lesson", slug="test-lesson", order=1):
    return Lesson.objects.create(
        title=title,
        slug=slug,
        summary="summary",
        content="<p>content</p>",
        order=order,
        quiz_questions={
            "questions": [
                {"question": "Q1", "options": ["a", "b", "c", "d"], "correct": 0},
                {"question": "Q2", "options": ["a", "b", "c", "d"], "correct": 1},
                {"question": "Q3", "options": ["a", "b", "c", "d"], "correct": 2},
            ]
        },
    )


class SeedLessonsTests(TestCase):
    def test_seed_creates_six_valid_lessons(self):
        call_command("seed_lessons")
        self.assertEqual(Lesson.objects.count(), 6)
        self.assertEqual(
            list(Lesson.objects.order_by("order").values_list("title", flat=True)),
            [
                "Budgeting Basics",
                "Saving & Emergency Funds",
                "Understanding Debt & Credit",
                "Investing Fundamentals",
                "Taxes & Your First Job",
                "Reading a Portfolio",
            ],
        )
        for lesson in Lesson.objects.all():
            questions = lesson.quiz_questions["questions"]
            self.assertEqual(len(questions), 3)
            for q in questions:
                self.assertIn(q["correct"], range(len(q["options"])))

    def test_seed_is_idempotent(self):
        call_command("seed_lessons")
        call_command("seed_lessons")
        self.assertEqual(Lesson.objects.count(), 6)


class StreakTests(TestCase):
    def setUp(self):
        self.user_id = uuid.uuid4()
        self.lesson = make_lesson()

    def test_first_attempt_starts_streak(self):
        streak = QuizAttempt.record_attempt(
            self.user_id, self.lesson, 100, at=timezone.now()
        )
        self.assertEqual(streak, 1)

    def test_next_day_increments_streak(self):
        now = timezone.now()
        QuizAttempt.record_attempt(self.user_id, self.lesson, 100, at=now)
        streak = QuizAttempt.record_attempt(
            self.user_id, self.lesson, 100, at=now + datetime.timedelta(days=1)
        )
        self.assertEqual(streak, 2)

    def test_same_day_keeps_streak(self):
        now = timezone.now()
        QuizAttempt.record_attempt(self.user_id, self.lesson, 100, at=now)
        streak = QuizAttempt.record_attempt(
            self.user_id, self.lesson, 66, at=now + datetime.timedelta(hours=2)
        )
        self.assertEqual(streak, 1)  # not inflated by same-day repeats

    def test_gap_resets_streak(self):
        now = timezone.now()
        QuizAttempt.record_attempt(self.user_id, self.lesson, 100, at=now)
        streak = QuizAttempt.record_attempt(
            self.user_id, self.lesson, 100, at=now + datetime.timedelta(days=3)
        )
        self.assertEqual(streak, 1)


class QuizApiTests(TestCase):
    def setUp(self):
        self.user_id = str(uuid.uuid4())
        self.lesson = make_lesson()
        self.client = APIClient()
        self.client.force_authenticate(user=SupabaseUser(id=self.user_id))

    def test_unauthorized_submission_is_401(self):
        res = APIClient().post(
            f"/api/lessons/{self.lesson.id}/attempt/", {"answers": [0, 1, 2]}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_perfect_score_records_attempt_and_streak(self):
        res = self.client.post(
            f"/api/lessons/{self.lesson.id}/attempt/", {"answers": [0, 1, 2]}, format="json"
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["score"], 100)
        self.assertEqual(res.data["correct"], 3)
        self.assertEqual(res.data["total"], 3)
        self.assertEqual(res.data["streak"], 1)
        attempt = QuizAttempt.objects.get(user_id=self.user_id)
        self.assertEqual(attempt.lesson, self.lesson)
        self.assertEqual(attempt.score, 100)
        self.assertEqual(attempt.streak_count, 1)

    def test_partial_score(self):
        res = self.client.post(
            f"/api/lessons/{self.lesson.id}/attempt/", {"answers": [3, 3, 3]}, format="json"
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["score"], 0)

        res = self.client.post(
            f"/api/lessons/{self.lesson.id}/attempt/", {"answers": [0, 0, 0]}, format="json"
        )
        self.assertEqual(res.data["score"], round(100 / 3))

    def test_missing_answers_rejected(self):
        res = self.client.post(
            f"/api/lessons/{self.lesson.id}/attempt/", {}, format="json"
        )
        self.assertEqual(res.status_code, 400)

    def test_my_attempts_returns_best_scores(self):
        self.client.post(
            f"/api/lessons/{self.lesson.id}/attempt/", {"answers": [0, 1, 2]}, format="json"
        )
        self.client.post(
            f"/api/lessons/{self.lesson.id}/attempt/", {"answers": [0, 0, 0]}, format="json"
        )
        res = self.client.get("/api/lessons/attempts/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["current_streak"], 1)
        lesson_row = [l for l in res.data["lessons"] if l["lesson_id"] == self.lesson.id][0]
        self.assertEqual(lesson_row["best_score"], 100)

    def test_lesson_pages_render_publicly(self):
        self.assertEqual(self.client.get("/learn/").status_code, 200)
        detail = self.client.get(f"/learn/{self.lesson.slug}/")
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "Q1")
        self.assertContains(detail, 'id="quiz-data"')
