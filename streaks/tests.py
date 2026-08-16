import datetime
import uuid

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from core.auth import SupabaseUser
from invest.models import Holding, Instrument, VirtualPortfolio
from learn.models import Lesson, QuizAttempt
from track.models import Budget, Category
from .models import Profile


def make_lesson(i):
    return Lesson.objects.create(
        title=f"Lesson {i}",
        slug=f"lesson-{i}",
        content="<p>x</p>",
        order=i,
        quiz_questions={
            "questions": [
                {"question": "Q", "options": ["a", "b", "c", "d"], "correct": 0}
                for _ in range(3)
            ]
        },
    )


class ProfileStreakTests(TestCase):
    def setUp(self):
        self.user_id = uuid.uuid4()
        self.profile = Profile.get_or_create_for(self.user_id)

    def test_first_activity_starts_streak(self):
        self.assertEqual(self.profile.record_activity(), 1)

    def test_same_day_keeps_streak(self):
        now = timezone.now()
        self.profile.record_activity(at=now)
        self.assertEqual(
            self.profile.record_activity(at=now + datetime.timedelta(hours=3)), 1
        )

    def test_next_day_increments(self):
        now = timezone.now()
        self.profile.record_activity(at=now)
        self.assertEqual(
            self.profile.record_activity(at=now + datetime.timedelta(days=1)), 2
        )
        self.assertEqual(
            self.profile.record_activity(at=now + datetime.timedelta(days=2)), 3
        )

    def test_gap_resets(self):
        now = timezone.now()
        self.profile.record_activity(at=now)
        self.assertEqual(
            self.profile.record_activity(at=now + datetime.timedelta(days=4)), 1
        )

    def test_reset_stale_streaks(self):
        now = timezone.now()
        active = Profile.get_or_create_for(uuid.uuid4())
        stale = Profile.get_or_create_for(uuid.uuid4())
        active.record_activity(at=now)
        stale.record_activity(at=now - datetime.timedelta(days=3))

        self.assertEqual(Profile.reset_stale_streaks(at=now), 1)
        stale.refresh_from_db()
        active.refresh_from_db()
        self.assertEqual(stale.streak_count, 0)
        self.assertEqual(active.streak_count, 1)


class BadgeTests(TestCase):
    def setUp(self):
        self.user_id = uuid.uuid4()
        self.profile = Profile.get_or_create_for(self.user_id)

    def test_seven_day_streak_badge(self):
        now = timezone.now()
        for day in range(6):
            self.profile.record_activity(at=now + datetime.timedelta(days=day))
        self.assertEqual(self.profile.evaluate_badges(), [])
        self.profile.record_activity(at=now + datetime.timedelta(days=6))
        self.assertEqual(self.profile.evaluate_badges(), ["7-Day Streak"])
        self.assertEqual(self.profile.evaluate_badges(), [])  # idempotent

    def test_budget_keeper_badge(self):
        category, _ = Category.objects.get_or_create(name="Food", defaults={"kind": "expense"})
        Budget.objects.create(user_id=self.user_id, category=category, monthly_limit=1000)
        self.assertEqual(self.profile.evaluate_badges(), ["Budget Keeper"])

    def test_first_trade_badge(self):
        portfolio = VirtualPortfolio.objects.create(user_id=self.user_id)
        instrument, _ = Instrument.objects.get_or_create(
            yahoo_symbol="SIM-TEST",
            defaults={"symbol": "TESTCO", "name": "Testco Ltd", "base_price": "2500"},
        )
        Holding.objects.create(
            portfolio=portfolio, instrument=instrument, quantity=10, avg_price=2500
        )
        self.assertEqual(self.profile.evaluate_badges(), ["First Trade"])

    def test_course_complete_badge(self):
        lessons = [make_lesson(i) for i in range(1, 7)]
        for lesson in lessons[:5]:
            QuizAttempt.record_attempt(self.user_id, lesson, 100)
        self.assertEqual(self.profile.evaluate_badges(), [])
        QuizAttempt.record_attempt(self.user_id, lessons[5], 100)
        self.assertEqual(self.profile.evaluate_badges(), ["Course Complete"])


class ProfileApiTests(TestCase):
    def setUp(self):
        self.user_id = str(uuid.uuid4())
        self.client = APIClient()
        self.client.force_authenticate(user=SupabaseUser(id=self.user_id))

    def test_profile_requires_auth(self):
        self.assertEqual(APIClient().get("/api/profile/").status_code, 401)

    def test_profile_returns_streak_and_badges(self):
        res = self.client.get("/api/profile/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["streak_count"], 0)
        self.assertEqual(
            set(res.data["badges"].keys()),
            {"7-Day Streak", "Budget Keeper", "First Trade", "Course Complete"},
        )

    def test_quiz_attempt_returns_unlocked_badges(self):
        lessons = [make_lesson(i) for i in range(1, 7)]
        res = None
        for lesson in lessons:
            res = self.client.post(
                f"/api/lessons/{lesson.id}/attempt/", {"answers": [0, 0, 0]}, format="json"
            )
            self.assertEqual(res.status_code, 200)
        self.assertIn("Course Complete", res.data["unlocked_badges"])
        self.assertEqual(res.data["streak"], 1)  # same-day attempts don't inflate


class CronTests(TestCase):
    def setUp(self):
        self.user_id = str(uuid.uuid4())
        profile = Profile.get_or_create_for(self.user_id)
        profile.record_activity(at=timezone.now() - datetime.timedelta(days=5))

    @override_settings(CRON_SECRET="topsecret", DEBUG=False)
    def test_cron_requires_secret_and_resets(self):
        self.assertEqual(APIClient().post("/api/cron/streaks/").status_code, 401)
        res = APIClient().post("/api/cron/streaks/", HTTP_AUTHORIZATION="Bearer topsecret")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["reset"], 1)

    @override_settings(CRON_SECRET="", DEBUG=False)
    def test_cron_refuses_without_configured_secret(self):
        self.assertEqual(APIClient().post("/api/cron/streaks/").status_code, 500)
