import uuid

from django.conf import settings
from django.db import models


class AbbreviationCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    parent = models.ForeignKey(
        "self",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="children",
    )
    display_order = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ("display_order", "name")
        verbose_name_plural = "abbreviation categories"

    def __str__(self):
        return self.name


class AbbreviationProfile(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    categories = models.ManyToManyField(
        AbbreviationCategory, blank=True, related_name="profiles"
    )
    preferred_entries = models.ManyToManyField(
        "AbbreviationEntry", blank=True, related_name="preferred_in_profiles"
    )
    excluded_entries = models.ManyToManyField(
        "AbbreviationEntry", blank=True, related_name="excluded_from_profiles"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="created_abbreviation_profiles",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class AbbreviationEntry(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        DRAFT = "draft", "Draft"

    abbreviation = models.CharField(max_length=100, db_index=True)
    full_form = models.CharField(max_length=500, db_index=True)
    normalized_abbreviation = models.CharField(
        max_length=100, db_index=True, editable=False
    )
    normalized_full_form = models.CharField(
        max_length=500, db_index=True, editable=False
    )
    category = models.ForeignKey(
        AbbreviationCategory,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="entries",
    )
    profiles = models.ManyToManyField(
        AbbreviationProfile, blank=True, related_name="entries"
    )
    service = models.CharField(max_length=50, blank=True)
    context = models.TextField(blank=True)
    case_sensitive = models.BooleanField(default=False)
    is_ambiguous = models.BooleanField(default=False)
    is_preferred = models.BooleanField(default=False)
    priority = models.IntegerField(default=0)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ACTIVE
    )
    source_name = models.CharField(max_length=150, blank=True)
    source_section = models.CharField(max_length=150, blank=True)
    source_page = models.PositiveIntegerField(blank=True, null=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="created_abbreviation_entries",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="updated_abbreviation_entries",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("abbreviation", "-is_preferred", "-priority", "full_form")
        constraints = [
            models.UniqueConstraint(
                fields=("normalized_abbreviation", "normalized_full_form"),
                name="unique_normalized_abbreviation_pair",
            )
        ]
        permissions = [
            ("access_abbreviation_tool", "Can access SD Checker"),
            ("process_document", "Can process DOCX documents"),
            ("search_dictionary", "Can search abbreviation dictionary"),
            ("manage_dictionary", "Can manage abbreviation dictionary"),
            ("import_dictionary", "Can import abbreviation dictionary"),
            ("export_dictionary", "Can export abbreviation dictionary"),
            ("manage_profiles", "Can manage abbreviation profiles"),
            ("view_audit_log", "Can view abbreviation audit log"),
        ]

    @staticmethod
    def normalize(value):
        return " ".join(value.casefold().split())

    def save(self, *args, **kwargs):
        self.abbreviation = " ".join(self.abbreviation.split())
        self.full_form = " ".join(self.full_form.split())
        self.normalized_abbreviation = self.normalize(self.abbreviation)
        self.normalized_full_form = self.normalize(self.full_form)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.abbreviation} — {self.full_form}"


class AbbreviationVariant(models.Model):
    class VariantType(models.TextChoices):
        ABBREVIATION = "alternative_abbreviation", "Alternative abbreviation"
        FULL_FORM = "alternative_full_form", "Alternative full form"
        PLURAL = "plural", "Plural"
        POSSESSIVE = "possessive", "Possessive"
        HYPHENATED = "hyphenated", "Hyphenated"
        LEGACY = "legacy", "Legacy"
        SERVICE = "service_specific", "Service-specific"
        SPELLING = "spelling", "Spelling variant"

    entry = models.ForeignKey(
        AbbreviationEntry, on_delete=models.CASCADE, related_name="variants"
    )
    variant = models.CharField(max_length=500)
    normalized_variant = models.CharField(max_length=500, db_index=True, editable=False)
    variant_type = models.CharField(max_length=30, choices=VariantType.choices)
    case_sensitive = models.BooleanField(default=False)
    status = models.CharField(
        max_length=10,
        choices=AbbreviationEntry.Status.choices,
        default=AbbreviationEntry.Status.ACTIVE,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("entry", "normalized_variant", "variant_type"),
                name="unique_abbreviation_variant",
            )
        ]

    def save(self, *args, **kwargs):
        self.variant = " ".join(self.variant.split())
        self.normalized_variant = AbbreviationEntry.normalize(self.variant)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.variant


class DocumentProcessingSession(models.Model):
    class Policy(models.TextChoices):
        ALL = "all", "Replace all eligible occurrences"
        KEEP_FIRST = "keep_first", "Keep first occurrence in full"
        DEFINE_FIRST = "define_first", "Full form with abbreviation on first use"

    class Operation(models.TextChoices):
        ABBREVIATE = "abbreviate", "Abbreviate"
        DEABBREVIATE = "deabbreviate", "Deabbreviate"

    class Status(models.TextChoices):
        CREATED = "created", "Created"
        ANALYSING = "analysing", "Analysing"
        REVIEW = "review", "Review"
        GENERATING = "generating", "Generating"
        COMPLETE = "complete", "Complete"
        FAILED = "failed", "Failed"
        DELETED = "deleted", "Deleted"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="abbreviation_sessions",
    )
    original_filename = models.CharField(max_length=255)
    operation_type = models.CharField(max_length=20, choices=Operation.choices)
    profile = models.ForeignKey(
        AbbreviationProfile, blank=True, null=True, on_delete=models.SET_NULL
    )
    replacement_policy = models.CharField(
        max_length=20, choices=Policy.choices, default=Policy.DEFINE_FIRST
    )
    processing_options = models.JSONField(default=dict, blank=True)
    file_size = models.PositiveBigIntegerField(default=0)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.CREATED
    )
    suggestion_count = models.PositiveIntegerField(default=0)
    accepted_count = models.PositiveIntegerField(default=0)
    rejected_count = models.PositiveIntegerField(default=0)
    ambiguous_count = models.PositiveIntegerField(default=0)
    unsupported_element_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    completed_at = models.DateTimeField(blank=True, null=True)
    deleted_at = models.DateTimeField(blank=True, null=True)


class ProcessingSuggestion(models.Model):
    class ReviewStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
        EDITED = "edited", "Edited"
        IGNORED = "ignored", "Ignored"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        DocumentProcessingSession, on_delete=models.CASCADE, related_name="suggestions"
    )
    abbreviation_entry = models.ForeignKey(
        AbbreviationEntry, blank=True, null=True, on_delete=models.SET_NULL
    )
    operation_type = models.CharField(
        max_length=20, choices=DocumentProcessingSession.Operation.choices
    )
    original_text = models.CharField(max_length=500)
    proposed_text = models.CharField(max_length=500)
    user_modified_text = models.CharField(max_length=500, blank=True)
    container_type = models.CharField(max_length=30)
    container_identifier = models.CharField(max_length=255)
    paragraph_identifier = models.CharField(max_length=255)
    start_offset = models.PositiveIntegerField()
    end_offset = models.PositiveIntegerField()
    confidence = models.DecimalField(max_digits=5, decimal_places=2)
    ambiguity_status = models.CharField(max_length=30, blank=True)
    selected_meaning = models.ForeignKey(
        AbbreviationEntry,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="selected_for_suggestions",
    )
    review_status = models.CharField(
        max_length=10, choices=ReviewStatus.choices, default=ReviewStatus.PENDING
    )
    mixed_format_warning = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class AbbreviationAuditLog(models.Model):
    abbreviation_entry = models.ForeignKey(
        AbbreviationEntry,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=50)
    previous_value = models.JSONField(blank=True, null=True)
    new_value = models.JSONField(blank=True, null=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, blank=True, null=True, on_delete=models.SET_NULL
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-timestamp",)


class Feedback(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="abbreviation_feedback",
    )
    name = models.CharField(max_length=150)
    email = models.EmailField(blank=True)
    message = models.TextField(max_length=4000)
    resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name_plural = "feedback"

    def __str__(self):
        return f"Feedback from {self.name}"
