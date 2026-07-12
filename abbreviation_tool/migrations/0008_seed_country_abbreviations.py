from django.db import migrations


COUNTRIES = (
    ("AF", "Afghanistan"), ("AU", "Australia"), ("BD", "Bangladesh"),
    ("BT", "Bhutan"), ("BR", "Brazil"), ("CA", "Canada"),
    ("CN", "China"), ("FR", "France"), ("DE", "Germany"),
    ("IN", "India"), ("ID", "Indonesia"), ("IT", "Italy"),
    ("JP", "Japan"), ("MY", "Malaysia"), ("MV", "Maldives"),
    ("MM", "Myanmar"), ("NP", "Nepal"), ("NZ", "New Zealand"),
    ("PK", "Pakistan"), ("RU", "Russia"), ("SA", "Saudi Arabia"),
    ("SG", "Singapore"), ("ZA", "South Africa"), ("KR", "South Korea"),
    ("LK", "Sri Lanka"), ("TH", "Thailand"), ("TR", "Turkey"),
    ("AE", "United Arab Emirates"), ("UK", "United Kingdom"),
    ("US", "United States"), ("VN", "Vietnam"),
)


def seed_countries(apps, schema_editor):
    Entry = apps.get_model("abbreviation_tool", "AbbreviationEntry")
    Profile = apps.get_model("abbreviation_tool", "AbbreviationProfile")
    general = Profile.objects.filter(name="General").first()
    for abbreviation, full_form in COUNTRIES:
        entry, _ = Entry.objects.get_or_create(
            normalized_abbreviation=abbreviation.casefold(),
            normalized_full_form=full_form.casefold(),
            defaults={"abbreviation": abbreviation, "full_form": full_form, "service": "Country", "source_name": "ISO-style country code"},
        )
        if general:
            entry.profiles.add(general)


def remove_countries(apps, schema_editor):
    apps.get_model("abbreviation_tool", "AbbreviationEntry").objects.filter(service="Country", source_name="ISO-style country code").delete()


class Migration(migrations.Migration):
    dependencies = [("abbreviation_tool", "0007_feedback")]
    operations = [migrations.RunPython(seed_countries, remove_countries)]
