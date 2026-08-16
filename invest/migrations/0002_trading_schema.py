from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models


def delete_legacy_holdings(apps, schema_editor):
    """The Phase-5 Holding stub had no UI and no writers; any rows that exist
    (e.g. manual DB pokes) are meaningless against the new instrument schema."""
    Holding = apps.get_model("invest", "Holding")
    Holding.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("invest", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Instrument",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("symbol", models.CharField(max_length=24, unique=True)),
                ("name", models.CharField(max_length=80)),
                ("kind", models.CharField(choices=[("index", "Index"), ("stock", "Stock"), ("etf", "ETF")], default="stock", max_length=8)),
                ("yahoo_symbol", models.CharField(max_length=24, unique=True)),
                ("default_price", models.DecimalField(decimal_places=4, default=Decimal("0"), max_digits=14)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["kind", "symbol"],
            },
        ),
        migrations.CreateModel(
            name="PriceSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("price", models.DecimalField(decimal_places=4, max_digits=14)),
                ("source", models.CharField(default="yahoo", max_length=16)),
                ("fetched_at", models.DateTimeField(db_index=True)),
                ("instrument", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="snapshots", to="invest.instrument")),
            ],
            options={
                "ordering": ["-fetched_at"],
            },
        ),
        migrations.CreateModel(
            name="Order",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("user_id", models.UUIDField(db_index=True)),
                ("side", models.CharField(choices=[("buy", "Buy"), ("sell", "Sell")], max_length=6)),
                ("quantity", models.DecimalField(decimal_places=6, max_digits=18)),
                ("order_type", models.CharField(choices=[("market", "Market"), ("limit", "Limit"), ("stop_loss", "Stop Loss")], default="market", max_length=10)),
                ("status", models.CharField(choices=[("filled", "Filled"), ("pending", "Pending"), ("cancelled", "Cancelled")], default="filled", max_length=10)),
                ("price", models.DecimalField(decimal_places=4, max_digits=14)),
                ("note", models.CharField(blank=True, max_length=120)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("filled_at", models.DateTimeField(blank=True, null=True)),
                ("instrument", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="orders", to="invest.instrument")),
                ("portfolio", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="orders", to="invest.virtualportfolio")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.RunPython(delete_legacy_holdings, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="holding",
            name="symbol",
        ),
        migrations.AddField(
            model_name="holding",
            name="instrument",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="holdings", to="invest.instrument"),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="holding",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AddField(
            model_name="virtualportfolio",
            name="current_balance",
            field=models.DecimalField(decimal_places=2, default=Decimal("100000.00"), max_digits=14),
        ),
        migrations.AddField(
            model_name="virtualportfolio",
            name="starting_balance",
            field=models.DecimalField(decimal_places=2, default=Decimal("100000.00"), max_digits=14),
        ),
        migrations.AddField(
            model_name="virtualportfolio",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AlterUniqueTogether(
            name="holding",
            unique_together={("portfolio", "instrument")},
        ),
    ]
