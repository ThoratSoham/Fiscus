from django.conf import settings
from django.db.models import Sum
from django.shortcuts import render
from django.utils import timezone
from rest_framework import permissions, viewsets
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.generics import ListAPIView
from rest_framework.response import Response

from core.auth import SupabaseJWTAuthentication
from .models import Budget, Category, Expense
from .serializers import BudgetSerializer, CategorySerializer, ExpenseSerializer

AUTH = [SupabaseJWTAuthentication]
PERM = [permissions.IsAuthenticated]


def _month_start(dt):
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _shift_months(dt, n):
    month_index = dt.year * 12 + (dt.month - 1) + n
    year, month = divmod(month_index, 12)
    return dt.replace(year=year, month=month + 1, day=1)


class CategoryListView(ListAPIView):
    """Public reference data — no auth required."""

    queryset = Category.objects.all()
    serializer_class = CategorySerializer


class ExpenseViewSet(viewsets.ModelViewSet):
    authentication_classes = AUTH
    permission_classes = PERM
    serializer_class = ExpenseSerializer

    def get_queryset(self):
        return Expense.objects.filter(user_id=self.request.user.id)

    def perform_create(self, serializer):
        serializer.save(user_id=self.request.user.id)
        Budget.recompute_for_user(self.request.user.id)

    def perform_update(self, serializer):
        serializer.save()
        Budget.recompute_for_user(self.request.user.id)

    def perform_destroy(self, instance):
        instance.delete()
        Budget.recompute_for_user(self.request.user.id)


class BudgetViewSet(viewsets.ModelViewSet):
    authentication_classes = AUTH
    permission_classes = PERM
    serializer_class = BudgetSerializer

    def get_queryset(self):
        return Budget.objects.filter(user_id=self.request.user.id)

    def perform_create(self, serializer):
        serializer.save(user_id=self.request.user.id)
        Budget.recompute_for_user(self.request.user.id)

    def perform_update(self, serializer):
        serializer.save()
        Budget.recompute_for_user(self.request.user.id)


@api_view(["GET"])
@authentication_classes(AUTH)
@permission_classes(PERM)
def dashboard(request):
    """Aggregated numbers for the dashboard: budgets, charts, trend."""
    user_id = request.user.id
    now = timezone.now()
    month_start = _month_start(now)
    next_month = _shift_months(month_start, 1)

    expenses_this_month = Expense.objects.filter(
        user_id=user_id,
        type=Expense.Type.EXPENSE,
        date__gte=month_start.date(),
        date__lt=next_month.date(),
    )
    spent_total = float(expenses_this_month.aggregate(t=Sum("amount"))["t"] or 0)
    income_total = float(
        Expense.objects.filter(
            user_id=user_id,
            type=Expense.Type.INCOME,
            date__gte=month_start.date(),
            date__lt=next_month.date(),
        ).aggregate(t=Sum("amount"))["t"]
        or 0
    )

    spent_by_category = [
        {"name": row["category__name"], "total": float(row["total"])}
        for row in expenses_this_month.values("category__name")
        .annotate(total=Sum("amount"))
        .order_by("-total")
    ]

    budget_rows = []
    for b in Budget.objects.filter(user_id=user_id).select_related("category"):
        limit = float(b.monthly_limit)
        spent = float(b.spent)
        budget_rows.append(
            {
                "id": b.id,
                "category": b.category.name,
                "category_id": b.category_id,
                "limit": limit,
                "spent": spent,
                "percent": round(spent / limit * 100, 1) if limit else 0,
                "over": spent > limit,
            }
        )

    trend = []
    for i in range(5, -1, -1):
        start = _shift_months(month_start, -i)
        end = _shift_months(start, 1)
        total = float(
            Expense.objects.filter(
                user_id=user_id,
                type=Expense.Type.EXPENSE,
                date__gte=start.date(),
                date__lt=end.date(),
            ).aggregate(t=Sum("amount"))["t"]
            or 0
        )
        trend.append({"label": start.strftime("%b %Y"), "total": total})

    return Response(
        {
            "month": month_start.strftime("%B %Y"),
            "spent_total": spent_total,
            "income_total": income_total,
            "net": income_total - spent_total,
            "spent_by_category": spent_by_category,
            "budgets": budget_rows,
            "trend": trend,
        }
    )


def dashboard_page(request):
    """HTML shell — all data comes from the API via the browser's JWT."""
    return render(
        request,
        "track/dashboard.html",
        {
            "config": {
                "supabase_url": settings.SUPABASE_URL,
                "supabase_anon_key": settings.SUPABASE_ANON_KEY,
            }
        },
    )
