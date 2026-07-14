import json

from django.core.management.base import BaseCommand, CommandError

from home_ai.dictionary_provider import (
    DictionaryLookupError,
    normalise_payload,
    save_offline,
)


class Command(BaseCommand):
    help = "Import dictionaryapi.dev-compatible JSON into the offline dictionary"

    def add_arguments(self, parser):
        parser.add_argument(
            "file", help="JSON file containing API entries or groups of entries"
        )

    def handle(self, *args, **options):
        try:
            with open(options["file"], encoding="utf-8") as source:
                data = json.load(source)
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(str(exc)) from exc
        if not isinstance(data, list):
            raise CommandError("The input must be a JSON list.")

        # Accept one API response, or a list whose items are API response lists.
        groups = data if data and isinstance(data[0], list) else [data]
        imported = skipped = 0
        for group in groups:
            try:
                fallback = group[0].get("word", "unknown")
                save_offline(normalise_payload(group, fallback))
                imported += 1
            except (DictionaryLookupError, AttributeError, IndexError, TypeError):
                skipped += 1
        self.stdout.write(
            self.style.SUCCESS(f"Imported {imported} entries; skipped {skipped}.")
        )
