from django.db import models


class Abbreviation(models.Model):
    abbreviation = models.CharField(max_length=80, db_index=True)
    meaning = models.CharField(max_length=500)
    source_page = models.PositiveSmallIntegerField()
    source = models.CharField(max_length=40, default="JSSDM 2022, Annex 16A")

    class Meta:
        ordering = ("abbreviation", "meaning")
        constraints = [
            models.UniqueConstraint(
                fields=("abbreviation", "meaning"),
                name="unique_jssdm_abbreviation_meaning",
            )
        ]

    def __str__(self):
        return f"{self.abbreviation} — {self.meaning}"
