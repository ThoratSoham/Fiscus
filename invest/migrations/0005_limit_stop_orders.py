from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("invest", "0004_simulated_market"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="trigger_price",
            field=models.DecimalField(blank=True, decimal_places=4, max_digits=14, null=True),
        ),
        migrations.AlterField(
            model_name="order",
            name="price",
            field=models.DecimalField(blank=True, decimal_places=4, max_digits=14, null=True),
        ),
    ]
