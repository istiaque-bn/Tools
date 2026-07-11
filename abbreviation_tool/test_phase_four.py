import tempfile
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone
from .models import AbbreviationEntry, AbbreviationProfile, DocumentProcessingSession, ProcessingSuggestion
from .services.preview import build_preview
from .services.review import bulk_decide, decide, history_action
from .storage import save_original
from .test_phase_two import docx_upload


class ReviewServiceTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.override = override_settings(DOCX_ABBREVIATION_TEMP_ROOT=self.temp.name); self.override.enable()
        self.user = get_user_model().objects.create_user("review-user"); self.other = get_user_model().objects.create_user("review-other")
        self.profile = AbbreviationProfile.objects.get(name="General")
        self.entry = AbbreviationEntry.objects.create(abbreviation="HQ", full_form="Headquarters"); self.entry.profiles.add(self.profile)
        self.session = DocumentProcessingSession.objects.create(user=self.user, original_filename="review.docx", operation_type="deabbreviate", profile=self.profile, file_size=10, status="review", expires_at=timezone.now()+timedelta(minutes=30))
        save_original(self.session, docx_upload())
        self.suggestion = ProcessingSuggestion.objects.create(session=self.session, abbreviation_entry=self.entry, operation_type="deabbreviate", original_text="HQ", proposed_text="Headquarters", container_type="paragraph", container_identifier="word/document.xml:p0", paragraph_identifier="word/document.xml:p0", start_offset=0, end_offset=2, confidence=100, ambiguity_status="unambiguous")

    def tearDown(self):
        self.override.disable(); self.temp.cleanup()

    def test_accept_reject_edit_reset_and_counts(self):
        decide(self.session.id, self.user, self.suggestion.id, "accept"); self.session.refresh_from_db(); self.assertEqual(self.session.accepted_count, 1)
        decide(self.session.id, self.user, self.suggestion.id, "edit", "Main Headquarters"); self.suggestion.refresh_from_db(); self.assertEqual(self.suggestion.user_modified_text, "Main Headquarters")
        decide(self.session.id, self.user, self.suggestion.id, "reject"); self.session.refresh_from_db(); self.assertEqual(self.session.rejected_count, 1)
        decide(self.session.id, self.user, self.suggestion.id, "reset"); self.suggestion.refresh_from_db(); self.assertEqual(self.suggestion.review_status, "pending")

    def test_ambiguous_accept_requires_selected_meaning(self):
        self.suggestion.ambiguity_status = "ambiguous"; self.suggestion.save(update_fields=("ambiguity_status",))
        with self.assertRaises(ValidationError): decide(self.session.id, self.user, self.suggestion.id, "accept")
        alternative = AbbreviationEntry.objects.create(abbreviation="HQ", full_form="Harbour Quality", is_ambiguous=True)
        decide(self.session.id, self.user, self.suggestion.id, "accept", selected_meaning_id=alternative.id)
        self.suggestion.refresh_from_db(); self.assertEqual(self.suggestion.proposed_text, "Harbour Quality")

    def test_undo_and_redo(self):
        decide(self.session.id, self.user, self.suggestion.id, "accept"); history_action(self.session.id, self.user, "undo")
        self.suggestion.refresh_from_db(); self.assertEqual(self.suggestion.review_status, "pending")
        history_action(self.session.id, self.user, "redo"); self.suggestion.refresh_from_db(); self.assertEqual(self.suggestion.review_status, "accepted")

    def test_bulk_high_confidence_skips_ambiguous(self):
        ambiguous = ProcessingSuggestion.objects.create(session=self.session, abbreviation_entry=self.entry, operation_type="deabbreviate", original_text="HQ", proposed_text="Headquarters", container_type="paragraph", container_identifier="p2", paragraph_identifier="p2", start_offset=0, end_offset=2, confidence=60, ambiguity_status="ambiguous")
        bulk_decide(self.session.id, self.user, "accept", high_confidence=True); self.suggestion.refresh_from_db(); ambiguous.refresh_from_db()
        self.assertEqual(self.suggestion.review_status, "accepted"); self.assertEqual(ambiguous.review_status, "pending")

    def test_cross_user_service_access_is_denied(self):
        with self.assertRaises(DocumentProcessingSession.DoesNotExist): decide(self.session.id, self.other, self.suggestion.id, "accept")

    def test_preview_is_structured_and_marks_suggestion(self):
        preview = build_preview(self.session); self.assertEqual(preview[0].segments[0].suggestion_id, str(self.suggestion.id))
