from decimal import Decimal

from django.db import migrations, models

# (symbol, name, kind, sim_id, base_price, volatility, drift)
# Fictional-but-real-sounding roster with distinct risk "personalities":
# steady blue chips, high-vol growth names, a couple of cyclical losers.
ROSTER = [
    ("NIFTY-SIM", "Nifty Sim Index", "index", "SIM-01", "24500.0000", 0.010, 0.0003),
    ("BANKNIFTY-SIM", "Bank Nifty Sim Index", "index", "SIM-02", "52000.0000", 0.012, 0.0002),
    ("SENSEX-SIM", "Sensex Sim Index", "index", "SIM-03", "80000.0000", 0.009, 0.0003),
    ("ORBIT", "Orbit Motors", "stock", "SIM-04", "480.0000", 0.030, 0.0012),
    ("NIMBUS", "Nimbus Textiles", "stock", "SIM-05", "320.0000", 0.014, 0.0005),
    ("CREST", "Crest Pharma", "stock", "SIM-06", "1240.0000", 0.018, 0.0008),
    ("SOLARIS", "Solaris Energy", "stock", "SIM-07", "95.0000", 0.034, 0.0015),
    ("BLAZE", "Blaze Telecom", "stock", "SIM-08", "210.0000", 0.020, 0.0004),
    ("DUNE", "Dune Metals", "stock", "SIM-09", "610.0000", 0.022, -0.0002),
    ("KOVAI", "Kovai Bank", "stock", "SIM-10", "890.0000", 0.016, 0.0006),
    ("PIXEL", "Pixelworks Tech", "stock", "SIM-11", "1450.0000", 0.026, 0.0010),
    ("ARROW", "Arrow Foods", "stock", "SIM-12", "175.0000", 0.013, 0.0007),
    ("ZENITH", "Zenith Steel", "stock", "SIM-13", "530.0000", 0.019, -0.0001),
    ("MARSHAL", "Marshal Auto", "stock", "SIM-14", "720.0000", 0.021, 0.0009),
    ("NORDWIND", "Nordwind Air", "stock", "SIM-15", "265.0000", 0.024, 0.0003),
    ("VEGA", "Vega Realty", "stock", "SIM-16", "390.0000", 0.028, 0.0013),
]


def swap_roster(apps, schema_editor):
    """Retire the old real-NSE seed roster and install the simulated one."""
    Instrument = apps.get_model("invest", "Instrument")
    Instrument.objects.filter(is_active=True).update(is_active=False)
    for symbol, name, kind, sim_id, base, volatility, drift in ROSTER:
        Instrument.objects.update_or_create(
            yahoo_symbol=sim_id,
            defaults={
                "symbol": symbol,
                "name": name,
                "kind": kind,
                "base_price": base,
                "volatility": volatility,
                "drift": drift,
                "is_active": True,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("invest", "0003_seed_instruments"),
    ]

    operations = [
        migrations.AddField(
            model_name="instrument",
            name="base_price",
            field=models.DecimalField(decimal_places=4, default=Decimal("100"), max_digits=14),
        ),
        migrations.AddField(
            model_name="instrument",
            name="volatility",
            field=models.FloatField(default=0.015),
        ),
        migrations.AddField(
            model_name="instrument",
            name="drift",
            field=models.FloatField(default=0.0003),
        ),
        migrations.RemoveField(
            model_name="instrument",
            name="default_price",
        ),
        migrations.AddField(
            model_name="virtualportfolio",
            name="seed",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.DeleteModel(
            name="PriceSnapshot",
        ),
        migrations.RunPython(swap_roster, migrations.RunPython.noop),
    ]
