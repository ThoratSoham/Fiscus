from decimal import Decimal
from secrets import randbelow

from django.db import models


class Instrument(models.Model):
    """A tradable instrument in the simulated market.

    Per the Phase 6 spec: fictional-but-real-sounding companies + simulated
    indices, each with a 'personality' — base volatility and drift bias —
    that drives its seeded random walk (see invest/engine.py). No real
    market data anywhere.
    """

    class Kind(models.TextChoices):
        INDEX = "index", "Index"
        STOCK = "stock", "Stock"
        ETF = "etf", "ETF"

    symbol = models.CharField(max_length=24, unique=True)  # NIFTY-SIM, ORBIT, ...
    name = models.CharField(max_length=80)
    kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.STOCK)
    # Stable internal id for the deterministic price engine (was yahoo_symbol).
    yahoo_symbol = models.CharField(max_length=24, unique=True)  # SIM-01, SIM-02, ...
    base_price = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal("100"))  # S0
    volatility = models.FloatField(default=0.015)  # per-simulated-day sigma
    drift = models.FloatField(default=0.0003)      # per-simulated-day drift bias
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["kind", "symbol"]

    def __str__(self):
        return f"{self.symbol} ({self.kind})"


class VirtualPortfolio(models.Model):
    """A user's paper-trading account.

    `seed` makes each student's market private and deterministic: every
    price is a function of (seed, instrument, elapsed time), so two students
    never see the same price, yet each student's path is reproducible.
    Resetting re-rolls the seed — a genuinely fresh market, per the spec.
    """

    user_id = models.UUIDField(unique=True, db_index=True)  # Supabase auth uid
    name = models.CharField(max_length=80, default="My Portfolio")
    seed = models.PositiveIntegerField(default=0)
    starting_balance = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("100000.00")
    )
    current_balance = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("100000.00")
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def get_or_create_for(cls, user_id, starting=Decimal("100000.00")):
        portfolio, _ = cls.objects.get_or_create(
            user_id=user_id,
            defaults={"starting_balance": starting, "current_balance": starting},
        )
        if not portfolio.seed:
            portfolio.roll_seed()
        return portfolio

    def roll_seed(self):
        self.seed = randbelow(2**31) or 1
        self.save(update_fields=["seed", "updated_at"])
        return self.seed

    def reset(self):
        """Wipe positions + orders, restore the starting balance, and re-roll
        the market seed so a reset means a genuinely fresh market."""
        self.holdings.all().delete()
        self.orders.all().delete()
        self.current_balance = self.starting_balance
        self.seed = randbelow(2**31) or 1
        self.save(update_fields=["current_balance", "seed", "updated_at"])

    def __str__(self):
        return f"{self.name} ({self.user_id})"


class Holding(models.Model):
    """An open position. Shorts (negative quantity) arrive in a later build step."""

    portfolio = models.ForeignKey(
        VirtualPortfolio, on_delete=models.CASCADE, related_name="holdings"
    )
    instrument = models.ForeignKey(
        Instrument, on_delete=models.PROTECT, related_name="holdings"
    )
    quantity = models.DecimalField(max_digits=18, decimal_places=6)
    avg_price = models.DecimalField(max_digits=14, decimal_places=4)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("portfolio", "instrument")]

    def __str__(self):
        return f"{self.instrument.symbol} x{self.quantity}"


class Order(models.Model):
    """An order against a portfolio. Market orders fill instantly at the
    engine price; limit/stop-loss fields are reserved for the next build
    step (pending status)."""

    class Side(models.TextChoices):
        BUY = "buy", "Buy"
        SELL = "sell", "Sell"

    class Type(models.TextChoices):
        MARKET = "market", "Market"
        LIMIT = "limit", "Limit"
        STOP_LOSS = "stop_loss", "Stop Loss"

    class Status(models.TextChoices):
        FILLED = "filled", "Filled"
        PENDING = "pending", "Pending"
        CANCELLED = "cancelled", "Cancelled"

    user_id = models.UUIDField(db_index=True)
    portfolio = models.ForeignKey(
        VirtualPortfolio, on_delete=models.CASCADE, related_name="orders"
    )
    instrument = models.ForeignKey(
        Instrument, on_delete=models.PROTECT, related_name="orders"
    )
    side = models.CharField(max_length=6, choices=Side.choices)
    quantity = models.DecimalField(max_digits=18, decimal_places=6)
    order_type = models.CharField(
        max_length=10, choices=Type.choices, default=Type.MARKET
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.FILLED
    )
    # Limit/stop orders: the price that must be crossed before the order
    # fills (buy limit below / sell limit above / stop-loss below).
    trigger_price = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    price = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)  # fill price
    note = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    filled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.side.upper()} {self.quantity} {self.instrument.symbol} @ {self.price}"
