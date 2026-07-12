from django.conf import settings
from django.db import migrations


def grant_checker_access(apps, schema_editor):
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    Group = apps.get_model("auth", "Group")
    group = Group.objects.filter(name="DOCX Abbreviation Users").first()
    if group:
        group.user_set.add(*User.objects.all())


def revoke_checker_access(apps, schema_editor):
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    Group = apps.get_model("auth", "Group")
    group = Group.objects.filter(name="DOCX Abbreviation Users").first()
    if group:
        group.user_set.remove(*User.objects.all())


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
        ("abbreviation_tool", "0008_seed_country_abbreviations"),
    ]
    operations = [migrations.RunPython(grant_checker_access, revoke_checker_access)]
