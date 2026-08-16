from django.db import migrations

# Curated instrument list: the three headline indices + NSE large-caps.
# default_price is the last live quote captured at build time — used as the
# offline fallback when the free market-data feed is unreachable.
INSTRUMENTS = [
    # (symbol, name, kind, yahoo_symbol, default_price)
    ("NIFTY 50", "Nifty 50 Index", "index", "^NSEI", "24366.0000"),
    ("BANK NIFTY", "Nifty Bank Index", "index", "^NSEBANK", "57491.1000"),
    ("SENSEX", "BSE Sensex", "index", "^BSESN", "78009.2500"),
    ("RELIANCE", "Reliance Industries", "stock", "RELIANCE.NS", "1310.0000"),
    ("TCS", "Tata Consultancy Services", "stock", "TCS.NS", "2361.0000"),
    ("HDFCBANK", "HDFC Bank", "stock", "HDFCBANK.NS", "727.0000"),
    ("INFY", "Infosys", "stock", "INFY.NS", "1169.2000"),
    ("ICICIBANK", "ICICI Bank", "stock", "ICICIBANK.NS", "1417.0000"),
    ("SBIN", "State Bank of India", "stock", "SBIN.NS", "1067.7000"),
    ("LT", "Larsen & Toubro", "stock", "LT.NS", "4057.0000"),
    ("ITC", "ITC", "stock", "ITC.NS", "278.2000"),
    ("BHARTIARTL", "Bharti Airtel", "stock", "BHARTIARTL.NS", "1992.1000"),
    ("HINDUNILVR", "Hindustan Unilever", "stock", "HINDUNILVR.NS", "2077.0000"),
    ("MARUTI", "Maruti Suzuki", "stock", "MARUTI.NS", "13834.0000"),
]


def seed_instruments(apps, schema_editor):
    Instrument = apps.get_model("invest", "Instrument")
    for symbol, name, kind, yahoo_symbol, price in INSTRUMENTS:
        Instrument.objects.update_or_create(
            yahoo_symbol=yahoo_symbol,
            defaults={
                "symbol": symbol,
                "name": name,
                "kind": kind,
                "default_price": price,
                "is_active": True,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("invest", "0002_trading_schema"),
    ]

    operations = [
        migrations.RunPython(seed_instruments, migrations.RunPython.noop),
    ]
