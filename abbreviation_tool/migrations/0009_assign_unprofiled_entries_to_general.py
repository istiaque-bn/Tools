from django.db import migrations


def assign_general_profile(apps, schema_editor):
    Entry = apps.get_model("abbreviation_tool", "AbbreviationEntry")
    Profile = apps.get_model("abbreviation_tool", "AbbreviationProfile")
    general = Profile.objects.filter(name="General", active=True).first()
    if not general:
        return
    for entry in Entry.objects.filter(profiles__isnull=True).iterator():
        entry.profiles.add(general)


class Migration(migrations.Migration):
    dependencies = [("abbreviation_tool", "0008_seed_country_abbreviations")]
    operations = [migrations.RunPython(assign_general_profile, migrations.RunPython.noop)]
