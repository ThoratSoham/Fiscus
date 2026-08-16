from django.db import models


class VirtualPortfolio(models.Model):
    """A user's paper-trading portfolio. Stub for Phase 6 — no UI yet."""

    user_id = models.UUIDField(unique=True, db_index=True)  # Supabase auth uid
    name = models.CharField(max_length=80, default="My Portfolio")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.user_id})"


class Holding(models.Model):
    """A position inside a VirtualPortfolio. Stub for Phase 6 — no UI yet."""

    portfolio = models.ForeignKey(
        VirtualPortfolio, on_delete=models.CASCADE, related_name="holdings"
    )
    symbol = models.CharField(max_length=16, db_index=True)
    quantity = models.DecimalField(max_digits=18, decimal_places=6)
    avg_price = models.DecimalField(max_digits=14, decimal_places=4)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.symbol} x{self.quantity}"
