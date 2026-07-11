import tempfile
from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from .models import AbbreviationEntry, AbbreviationProfile, DocumentProcessingSession
from .services.analysis import analyse_session
from .storage import save_original, session_directory
from .test_phase_two import docx_upload


class FinalHardeningTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.override = override_settings(DOCX_ABBREVIATION_TEMP_ROOT=self.temp.name); self.override.enable()
        self.user = get_user_model().objects.create_user("hardened-user"); self.user.groups.add(Group.objects.get(name="DOCX Abbreviation Users"))
        self.profile = AbbreviationProfile.objects.get(name="General")
        entry = AbbreviationEntry.objects.create(abbreviation="HQ", full_form="Headquarters", is_ambiguous=True); entry.profiles.add(self.profile)

    def tearDown(self): self.override.disable(); self.temp.cleanup()

    def make_session(self, options=None):
        upload = docx_upload(); session = DocumentProcessingSession.objects.create(user=self.user, original_filename="safe.docx", operation_type="abbreviate", profile=self.profile, file_size=upload.size, processing_options=options or {}, expires_at=timezone.now()+timedelta(minutes=30)); save_original(session, upload); return session

    @override_settings(DOCX_ABBREVIATION_MAX_ACTIVE_SESSIONS=1)
    def test_active_session_limit(self):
        self.make_session(); self.client.force_login(self.user)
        response = self.client.post(reverse("abbreviation_tool:upload"), {})
        self.assertEqual(response.status_code, 429)

    @override_settings(DOCX_ABBREVIATION_MAX_SUGGESTIONS=0)
    def test_analysis_limit_failure_deletes_files_via_view(self):
        # The fixture text has no match, so patch analysis to exercise controlled failure cleanup.
        session = self.make_session(); self.client.force_login(self.user)
        from django.core.exceptions import ValidationError
        with patch("abbreviation_tool.views.analyse_session", side_effect=ValidationError("Safe limit reached.")):
            response = self.client.post(reverse("abbreviation_tool:analyse", args=[session.id]))
        self.assertEqual(response.status_code, 302); session.refresh_from_db()
        self.assertEqual(session.status, "failed"); self.assertIsNotNone(session.deleted_at); self.assertFalse(session_directory(session.id).exists())

    def test_force_case_sensitive_and_high_confidence_options(self):
        from abbreviation_tool.services.matching import candidates_for, find_matches, POLICY_ALL
        from abbreviation_tool.services.ooxml import CharacterLocation, TextContainer
        candidate = candidates_for(self.profile, "abbreviate", force_case_sensitive=True)
        text = "headquarters"; container = TextContainer("word/document.xml", "p", "paragraph", text, [CharacterLocation(0, i, b"") for i in range(len(text))])
        self.assertEqual(find_matches(container, candidate, "abbreviate", POLICY_ALL), [])

    def test_simple_upload_processes_and_downloads(self):
        import zipfile
        from io import BytesIO
        from django.core.files.uploadedfile import SimpleUploadedFile
        from abbreviation_tool.test_phase_two import CONTENT_TYPES, RELS, DOCX_MIME
        document = b'''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Headquarters</w:t></w:r></w:p></w:body></w:document>'''
        output = BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as package:
            package.writestr("[Content_Types].xml", CONTENT_TYPES); package.writestr("_rels/.rels", RELS); package.writestr("word/document.xml", document)
        upload = SimpleUploadedFile("simple.docx", output.getvalue(), content_type=DOCX_MIME)
        AbbreviationEntry.objects.filter(abbreviation="HQ").update(is_ambiguous=False)
        self.client.force_login(self.user)
        response = self.client.post(reverse("abbreviation_tool:landing"), {"operation_type": "abbreviate", "docx_file": upload})
        self.assertEqual(response.status_code, 200)
        processed = b"".join(response.streaming_content); response.close()
        with zipfile.ZipFile(BytesIO(processed)) as package:
            self.assertIn(b">HQ<", package.read("word/document.xml"))

    def test_two_way_text_converter(self):
        AbbreviationEntry.objects.filter(abbreviation="HQ").update(is_ambiguous=False)
        self.client.force_login(self.user)
        response = self.client.post(reverse("abbreviation_tool:text_convert"), '{"operation":"abbreviate","text":"Report to Headquarters."}', content_type="application/json")
        self.assertEqual(response.json()["result"], "Report to HQ.")
        response = self.client.post(reverse("abbreviation_tool:text_convert"), '{"operation":"deabbreviate","text":"Report to HQ."}', content_type="application/json")
        self.assertEqual(response.json()["result"], "Report to Headquarters.")

    @override_settings(DOCX_ABBREVIATION_TOOL_ENABLED=False)
    def test_disabled_feature_hides_dashboard_card(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("home"))
        self.assertNotContains(response, "SD Checker")
