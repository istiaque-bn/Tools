from django.db import models


class DictionaryEntry(models.Model):
    """Dictionary text stored locally; remote audio is not persisted."""

    word = models.CharField(max_length=80, unique=True, db_index=True)
    phonetic = models.CharField(max_length=160, blank=True)
    pronunciations = models.JSONField(default=list, blank=True)
    meanings = models.JSONField(default=list)
    source_urls = models.JSONField(default=list, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("word",)

    def __str__(self):
        return self.word
