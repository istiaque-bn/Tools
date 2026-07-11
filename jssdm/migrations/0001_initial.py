from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="Abbreviation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("abbreviation", models.CharField(db_index=True, max_length=80)),
                ("meaning", models.CharField(max_length=500)),
                ("source_page", models.PositiveSmallIntegerField()),
                ("source", models.CharField(default="JSSDM 2022, Annex 16A", max_length=40)),
            ],
            options={"ordering": ("abbreviation", "meaning")},
        ),
        migrations.AddConstraint(
            model_name="abbreviation",
            constraint=models.UniqueConstraint(fields=("abbreviation", "meaning"), name="unique_jssdm_abbreviation_meaning"),
        ),
    ]
