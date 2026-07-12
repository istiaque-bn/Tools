from django.db import migrations


def assign_all_to_general(apps, schema_editor):
    Entry = apps.get_model("abbreviation_tool", "AbbreviationEntry")
    Profile = apps.get_model("abbreviation_tool", "AbbreviationProfile")
    general = Profile.objects.filter(name="General", active=True).first()
    if not general:
        return
    general.entries.add(*Entry.objects.all())


class Migration(migrations.Migration):
    dependencies = [("abbreviation_tool", "0009_assign_unprofiled_entries_to_general")]
    operations = [migrations.RunPython(assign_all_to_general, migrations.RunPython.noop)]
