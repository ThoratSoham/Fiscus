from django.conf import settings
from django.shortcuts import get_object_or_404, render
from rest_framework import permissions
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from core.auth import SupabaseJWTAuthentication
from .models import Lesson, QuizAttempt

AUTH = [SupabaseJWTAuthentication]
PERM = [permissions.IsAuthenticated]


def _config():
    return {
        "supabase_url": settings.SUPABASE_URL,
        "supabase_anon_key": settings.SUPABASE_ANON_KEY,
    }


def lesson_list(request):
    return render(
        request,
        "learn/lesson_list.html",
        {"lessons": Lesson.objects.all(), "config": _config()},
    )


def lesson_detail(request, slug):
    lesson = get_object_or_404(Lesson, slug=slug)
    next_lesson = (
        Lesson.objects.filter(order__gt=lesson.order).order_by("order").first()
    )
    return render(
        request,
        "learn/lesson_detail.html",
        {"lesson": lesson, "next_lesson": next_lesson, "config": _config()},
    )


@api_view(["POST"])
@authentication_classes(AUTH)
@permission_classes(PERM)
def submit_quiz(request, pk):
    """Verify answers, record a QuizAttempt, and return score + streak."""
    lesson = get_object_or_404(Lesson, pk=pk)
    questions = lesson.quiz_questions.get("questions", [])
    if not questions:
        return Response({"detail": "This lesson has no quiz."}, status=400)

    answers = request.data.get("answers")
    if not isinstance(answers, list):
        return Response({"detail": "answers must be a list of option indices."}, status=400)

    correct = sum(
        1
        for i, q in enumerate(questions)
        if i < len(answers)
        and isinstance(answers[i], int)
        and answers[i] == q.get("correct")
    )
    score = round(correct / len(questions) * 100)
    streak = QuizAttempt.record_attempt(
        user_id=request.user.id, lesson=lesson, score=score
    )
    return Response(
        {"score": score, "correct": correct, "total": len(questions), "streak": streak}
    )


@api_view(["GET"])
@authentication_classes(AUTH)
@permission_classes(PERM)
def my_attempts(request):
    """Best score per lesson + current streak — powers list-page checkmarks."""
    attempts = list(
        QuizAttempt.objects.filter(user_id=request.user.id).select_related("lesson")
    )
    best = {}
    for a in attempts:
        best[a.lesson_id] = max(best.get(a.lesson_id, -1), a.score)
    current_streak = attempts[0].streak_count if attempts else 0
    return Response(
        {
            "current_streak": current_streak,
            "lessons": [
                {
                    "lesson_id": lesson.id,
                    "slug": lesson.slug,
                    "best_score": best.get(lesson.id),
                }
                for lesson in Lesson.objects.all()
            ],
        }
    )
