from django.db import migrations
from django.db.models import Count


PROFILE_NAMES = ("Joint", "Army", "Navy", "Air Force", "Administrative", "Operational", "Training", "General", "Custom")


def import_dictionary(apps, schema_editor):
    Category = apps.get_model("abbreviation_tool", "AbbreviationCategory")
    Profile = apps.get_model("abbreviation_tool", "AbbreviationProfile")
    Entry = apps.get_model("abbreviation_tool", "AbbreviationEntry")
    Legacy = apps.get_model("jssdm", "Abbreviation")
    category = Category.objects.create(name="General", description="General JSSDM abbreviations")
    profiles = {name: Profile.objects.create(name=name) for name in PROFILE_NAMES}
    profiles["General"].categories.add(category)
    objects = []
    for item in Legacy.objects.all().iterator():
        abbreviation = " ".join(item.abbreviation.split())
        full_form = " ".join(item.meaning.split())
        objects.append(Entry(
            abbreviation=abbreviation,
            full_form=full_form,
            normalized_abbreviation=" ".join(abbreviation.casefold().split()),
            normalized_full_form=" ".join(full_form.casefold().split()),
            category=category,
            source_name="JSSDM 2022",
            source_section="Section 16, Annex 16A",
            source_page=item.source_page,
        ))
    Entry.objects.bulk_create(objects, ignore_conflicts=True)
    ambiguous = Entry.objects.values("normalized_abbreviation").annotate(total=Count("id")).filter(total__gt=1).values_list("normalized_abbreviation", flat=True)
    Entry.objects.filter(normalized_abbreviation__in=ambiguous).update(is_ambiguous=True)
    general = profiles["General"]
    general.entries.add(*Entry.objects.all())


def reverse_import(apps, schema_editor):
    apps.get_model("abbreviation_tool", "AbbreviationEntry").objects.all().delete()
    apps.get_model("abbreviation_tool", "AbbreviationProfile").objects.filter(name__in=PROFILE_NAMES).delete()
    apps.get_model("abbreviation_tool", "AbbreviationCategory").objects.filter(name="General").delete()


class Migration(migrations.Migration):
    dependencies = [("abbreviation_tool", "0001_initial"), ("jssdm", "0001_initial")]
    operations = [migrations.RunPython(import_dictionary, reverse_import)]
