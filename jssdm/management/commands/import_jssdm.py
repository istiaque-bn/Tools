from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from jssdm.models import Abbreviation
from jssdm.parser import annex_abbreviations


class Command(BaseCommand):
    help = "Import abbreviations from Section 16, Annex A of JSSDM 2022."

    def add_arguments(self, parser):
        parser.add_argument("pdf", type=Path)

    def handle(self, *args, **options):
        pdf = options["pdf"]
        if not pdf.is_file():
            raise CommandError(f"PDF not found: {pdf}")
        rows = annex_abbreviations(pdf)
        if not rows:
            raise CommandError("No Annex 16A abbreviation rows were found.")
        unique_rows = list({(row["abbreviation"], row["meaning"]): row for row in rows}.values())
        Abbreviation.objects.all().delete()
        Abbreviation.objects.bulk_create(Abbreviation(**row) for row in unique_rows)
        self.stdout.write(self.style.SUCCESS(f"Imported {len(unique_rows)} unique JSSDM abbreviations."))
