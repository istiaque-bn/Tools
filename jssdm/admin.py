from django.contrib import admin

from .models import Abbreviation


@admin.register(Abbreviation)
class AbbreviationAdmin(admin.ModelAdmin):
    list_display = ("abbreviation", "meaning", "source_page")
    search_fields = ("abbreviation", "meaning")
    list_filter = ("source",)
