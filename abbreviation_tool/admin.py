from django.contrib import admin

from .models import (
    AbbreviationAuditLog,
    AbbreviationCategory,
    AbbreviationEntry,
    AbbreviationProfile,
    AbbreviationVariant,
    DocumentProcessingSession,
    Feedback,
)


class VariantInline(admin.TabularInline):
    model = AbbreviationVariant
    extra = 0


@admin.register(AbbreviationEntry)
class AbbreviationEntryAdmin(admin.ModelAdmin):
    list_display = (
        "abbreviation",
        "full_form",
        "service",
        "is_ambiguous",
        "is_preferred",
        "status",
        "source_page",
    )
    list_filter = ("status", "service", "is_ambiguous", "is_preferred", "category")
    search_fields = ("abbreviation", "full_form", "variants__variant")
    filter_horizontal = ("profiles",)
    readonly_fields = (
        "normalized_abbreviation",
        "normalized_full_form",
        "created_at",
        "updated_at",
    )
    inlines = (VariantInline,)

    def save_model(self, request, obj, form, change):
        before = None
        if change:
            old = AbbreviationEntry.objects.get(pk=obj.pk)
            before = {
                "abbreviation": old.abbreviation,
                "full_form": old.full_form,
                "status": old.status,
            }
        obj.updated_by = request.user
        if not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
        AbbreviationAuditLog.objects.create(
            abbreviation_entry=obj,
            action="updated" if change else "created",
            previous_value=before,
            new_value={
                "abbreviation": obj.abbreviation,
                "full_form": obj.full_form,
                "status": obj.status,
            },
            user=request.user,
        )

    def delete_model(self, request, obj):
        AbbreviationAuditLog.objects.create(
            abbreviation_entry=obj,
            action="deleted",
            previous_value={
                "abbreviation": obj.abbreviation,
                "full_form": obj.full_form,
                "status": obj.status,
            },
            user=request.user,
        )
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            AbbreviationAuditLog.objects.create(
                abbreviation_entry=obj,
                action="deleted",
                previous_value={
                    "abbreviation": obj.abbreviation,
                    "full_form": obj.full_form,
                    "status": obj.status,
                },
                user=request.user,
            )
        super().delete_queryset(request, queryset)


@admin.register(AbbreviationCategory)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "display_order", "active")
    list_filter = ("active",)
    search_fields = ("name", "description")


@admin.register(AbbreviationProfile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "active", "created_at")
    list_filter = ("active",)
    filter_horizontal = ("categories", "preferred_entries", "excluded_entries")


@admin.register(AbbreviationAuditLog)
class AuditAdmin(admin.ModelAdmin):
    list_display = ("abbreviation_entry", "action", "user", "timestamp")
    list_filter = ("action", "timestamp")
    search_fields = (
        "abbreviation_entry__abbreviation",
        "abbreviation_entry__full_form",
    )
    readonly_fields = (
        "abbreviation_entry",
        "action",
        "previous_value",
        "new_value",
        "user",
        "timestamp",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(DocumentProcessingSession)
class SessionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "operation_type",
        "status",
        "created_at",
        "expires_at",
    )
    readonly_fields = tuple(
        field.name for field in DocumentProcessingSession._meta.fields
    )

    def has_add_permission(self, request):
        return False


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "user", "resolved", "created_at")
    list_filter = ("resolved", "created_at")
    search_fields = ("name", "email", "message")
    readonly_fields = ("user", "name", "email", "message", "created_at")
