from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="DictionaryEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("word", models.CharField(db_index=True, max_length=80, unique=True)),
                ("phonetic", models.CharField(blank=True, max_length=160)),
                ("pronunciations", models.JSONField(blank=True, default=list)),
                ("meanings", models.JSONField(default=list)),
                ("source_urls", models.JSONField(blank=True, default=list)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ("word",)},
        )
    ]
