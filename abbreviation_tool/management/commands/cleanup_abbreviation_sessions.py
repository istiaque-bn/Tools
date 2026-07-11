from django.core.management.base import BaseCommand

from abbreviation_tool.storage import cleanup_expired


class Command(BaseCommand):
    help = "Delete expired DOCX Abbreviation Manager files and suggestion records."

    def handle(self, *args, **options):
        count = cleanup_expired()
        self.stdout.write(self.style.SUCCESS(f"Cleaned {count} expired DOCX processing sessions."))
