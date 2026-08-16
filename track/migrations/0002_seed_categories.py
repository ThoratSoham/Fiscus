from django.db import migrations

DEFAULT_CATEGORIES = [
    ("Food", "expense"),
    ("Transport", "expense"),
    ("Housing", "expense"),
    ("Utilities", "expense"),
    ("Entertainment", "expense"),
    ("Health", "expense"),
    ("Education", "expense"),
    ("Shopping", "expense"),
    ("Income", "income"),
    ("Other", "both"),
]


def seed_categories(apps, schema_editor):
    Category = apps.get_model("track", "Category")
    for name, kind in DEFAULT_CATEGORIES:
        Category.objects.get_or_create(name=name, defaults={"kind": kind})


def unseed_categories(apps, schema_editor):
    Category = apps.get_model("track", "Category")
    Category.objects.filter(name__in=[name for name, _ in DEFAULT_CATEGORIES]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("track", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_categories, reverse_code=unseed_categories),
    ]
