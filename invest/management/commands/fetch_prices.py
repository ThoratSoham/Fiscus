from django.core.management.base import BaseCommand

from invest.prices import refresh_all


class Command(BaseCommand):
    help = "Fetch the latest prices for all active instruments and store snapshots."

    def handle(self, *args, **options):
        results = refresh_all()
        ok = sum(1 for value in results.values() if value)
        self.stdout.write(
            self.style.SUCCESS(f"Refreshed {ok}/{len(results)} instruments.")
        )
        if ok < len(results):
            self.stdout.write(
                self.style.WARNING(
                    f"{len(results) - ok} instruments could not be refreshed — "
                    "the free feed is rate-limited or unreachable. They will "
                    "fall back to their last known snapshot / default price."
                )
            )
