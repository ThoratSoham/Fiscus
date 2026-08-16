from django.db import models
from django.db.models import Sum
from django.utils import timezone


class Category(models.Model):
    """Reference data: the spend categories users pick from (global list)."""

    class Kind(models.TextChoices):
        EXPENSE = "expense", "Expense"
        INCOME = "income", "Income"
        BOTH = "both", "Both"

    name = models.CharField(max_length=64, unique=True)
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.EXPENSE)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Expense(models.Model):
    """A single income/expense entry, owned by a Supabase user id."""

    class Type(models.TextChoices):
        EXPENSE = "expense", "Expense"
        INCOME = "income", "Income"

    user_id = models.UUIDField(db_index=True)  # Supabase auth uid (auth.uid())
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="expenses",
        null=True, blank=True,
    )
    type = models.CharField(max_length=16, choices=Type.choices, default=Type.EXPENSE)
    date = models.DateField(default=timezone.localdate)
    note = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.type}: {self.amount} ({self.category})"


class Budget(models.Model):
    """Per-category monthly budget: (category, monthly_limit, spent, user)."""

    user_id = models.UUIDField(db_index=True)  # Supabase auth uid
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="budgets")
    monthly_limit = models.DecimalField(max_digits=10, decimal_places=2)
    spent = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        ordering = ["category__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["user_id", "category"], name="uniq_budget_user_category"
            )
        ]

    def __str__(self):
        return f"{self.category}: {self.spent}/{self.monthly_limit}"

    @classmethod
    def recompute_for_user(cls, user_id, now=None):
        """Sync every budget's `spent` to the current month's expense total."""
        now = now or timezone.now()
        totals = dict(
            Expense.objects.filter(
                user_id=user_id,
                type=Expense.Type.EXPENSE,
                date__year=now.year,
                date__month=now.month,
            )
            .values("category_id")
            .annotate(total=Sum("amount"))
            .values_list("category_id", "total")
        )
        for budget in cls.objects.filter(user_id=user_id):
            budget.spent = totals.get(budget.category_id, 0)
            budget.save(update_fields=["spent"])
