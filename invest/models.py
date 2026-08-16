from decimal import Decimal

from django.db import models


class Instrument(models.Model):
    """A tradable instrument: an NSE index or a curated NSE large-cap stock."""

    class Kind(models.TextChoices):
        INDEX = "index", "Index"
        STOCK = "stock", "Stock"
        ETF = "etf", "ETF"

    symbol = models.CharField(max_length=24, unique=True)  # display: NIFTY 50, RELIANCE
    name = models.CharField(max_length=80)
    kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.STOCK)
    yahoo_symbol = models.CharField(max_length=24, unique=True)  # ^NSEI, RELIANCE.NS
    # Offline fallback price — seeded from real quotes so the app still works
    # when the free market-data feed is unreachable.
    default_price = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal("0"))
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["kind", "symbol"]

    def __str__(self):
        return f"{self.symbol} ({self.kind})"


class PriceSnapshot(models.Model):
    """One stored quote per fetch. The newest row per instrument is the live price."""

    instrument = models.ForeignKey(
        Instrument, on_delete=models.CASCADE, related_name="snapshots"
    )
    price = models.DecimalField(max_digits=14, decimal_places=4)
    source = models.CharField(max_length=16, default="yahoo")
    fetched_at = models.DateTimeField(db_index=True)

    class Meta:
        ordering = ["-fetched_at"]

    def __str__(self):
        return f"{self.instrument.symbol} @ {self.price} ({self.fetched_at:%H:%M})"


class VirtualPortfolio(models.Model):
    """A user's paper-trading account: cash + positions.

    Starting balance is set once (custom per user) and every P&L / return
    figure is relative to it.
    """

    user_id = models.UUIDField(unique=True, db_index=True)  # Supabase auth uid
    name = models.CharField(max_length=80, default="My Portfolio")
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
        return portfolio

    def reset(self):
        """Wipe all positions + orders and restore the starting balance."""
        self.holdings.all().delete()
        self.orders.all().delete()
        self.current_balance = self.starting_balance
        self.save(update_fields=["current_balance", "updated_at"])

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
    latest snapshot price; limit/stop-loss fields are reserved for the next
    build step (pending status)."""

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
    price = models.DecimalField(max_digits=14, decimal_places=4)  # fill price
    note = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    filled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.side.upper()} {self.quantity} {self.instrument.symbol} @ {self.price}"
