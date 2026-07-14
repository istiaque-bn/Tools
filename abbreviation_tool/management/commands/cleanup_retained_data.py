from django.core.management.base import BaseCommand

from abbreviation_tool.storage import cleanup_expired


class Command(BaseCommand):
    help = "Delete expired temporary uploads and generated document files"

    def handle(self, *args, **options):
        count = cleanup_expired()
        self.stdout.write(
            self.style.SUCCESS(f"Removed {count} expired processing resources.")
        )
