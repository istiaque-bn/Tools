from django.conf import settings
from django.db import migrations


def assign_standard_group(apps, schema_editor):
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    Group = apps.get_model("auth", "Group")
    group, _ = Group.objects.get_or_create(name="DOCX Abbreviation Users")
    for user in User.objects.filter(is_superuser=False).iterator():
        user.groups.add(group)


def unassign_standard_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    group = Group.objects.filter(name="DOCX Abbreviation Users").first()
    if group:
        group.user_set.clear()


class Migration(migrations.Migration):
    dependencies = [("abbreviation_tool", "0003_documentprocessingsession_processing_options_and_more")]
    operations = [migrations.RunPython(assign_standard_group, unassign_standard_group)]
