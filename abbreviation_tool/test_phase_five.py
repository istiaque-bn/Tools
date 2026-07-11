import hashlib
import tempfile
import zipfile
from datetime import timedelta
from io import BytesIO
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from lxml import etree
from .models import AbbreviationEntry, AbbreviationProfile, DocumentProcessingSession, ProcessingSuggestion
from .services.generation import generate_session
from .storage import save_original, session_directory
from .test_phase_two import CONTENT_TYPES, DOCX_MIME, RELS


DOCUMENT_XML = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p w:rsidR="1234"><w:pPr><w:pStyle w:val="Heading1"/><w:spacing w:after="240"/></w:pPr><w:r><w:rPr><w:b/><w:sz w:val="28"/></w:rPr><w:t xml:space="preserve">Bangladesh </w:t></w:r><w:r><w:rPr><w:i/></w:rPr><w:t>Armed Forces</w:t></w:r><w:r><w:t xml:space="preserve"> and Headquarters.</w:t></w:r></w:p><w:sectPr><w:pgSz w:w="16838" w:h="11906" w:orient="landscape"/><w:pgMar w:top="720" w:right="900" w:bottom="720" w:left="900"/></w:sectPr></w:body></w:document>'''


def complex_docx():
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", CONTENT_TYPES); package.writestr("_rels/.rels", RELS); package.writestr("word/document.xml", DOCUMENT_XML)
        package.writestr("word/header1.xml", b"unchanged-header"); package.writestr("word/footer1.xml", b"unchanged-footer"); package.writestr("word/media/image1.png", b"unchanged-image")
    from django.core.files.uploadedfile import SimpleUploadedFile
    return SimpleUploadedFile("formatted.docx", output.getvalue(), content_type=DOCX_MIME)


class GenerationTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.override = override_settings(DOCX_ABBREVIATION_TEMP_ROOT=self.temp.name); self.override.enable()
        self.user = get_user_model().objects.create_user("generation-user"); self.user.groups.add(Group.objects.get(name="DOCX Abbreviation Users"))
        self.other = get_user_model().objects.create_user("generation-other")
        self.profile = AbbreviationProfile.objects.get(name="General")
        self.baf = AbbreviationEntry.objects.create(abbreviation="BAF", full_form="Bangladesh Armed Forces"); self.hq = AbbreviationEntry.objects.create(abbreviation="HQ", full_form="Headquarters")
        self.session = DocumentProcessingSession.objects.create(user=self.user, original_filename="formatted.docx", operation_type="abbreviate", profile=self.profile, file_size=500, status="review", accepted_count=2, expires_at=timezone.now()+timedelta(minutes=30))
        save_original(self.session, complex_docx())
        ProcessingSuggestion.objects.create(session=self.session, abbreviation_entry=self.baf, operation_type="abbreviate", original_text="Bangladesh Armed Forces", proposed_text="BAF", container_type="paragraph", container_identifier="word/document.xml:p0", paragraph_identifier="word/document.xml:p0", start_offset=0, end_offset=23, confidence=100, ambiguity_status="unambiguous", review_status="accepted", mixed_format_warning=True)
        ProcessingSuggestion.objects.create(session=self.session, abbreviation_entry=self.hq, operation_type="abbreviate", original_text="Headquarters", proposed_text="HQ", user_modified_text="Main HQ", container_type="paragraph", container_identifier="word/document.xml:p0", paragraph_identifier="word/document.xml:p0", start_offset=28, end_offset=40, confidence=100, ambiguity_status="unambiguous", review_status="edited")

    def tearDown(self): self.override.disable(); self.temp.cleanup()

    def test_generation_preserves_formatting_and_unchanged_parts(self):
        original = session_directory(self.session.id) / "original.docx"
        with zipfile.ZipFile(original) as package: hashes = {name: hashlib.sha256(package.read(name)).digest() for name in ("word/header1.xml", "word/footer1.xml", "word/media/image1.png")}
        output = generate_session(self.session.id, self.user)
        with zipfile.ZipFile(output) as package:
            root = etree.fromstring(package.read("word/document.xml")); self.assertIn("BAF and Main HQ.", "".join(root.itertext()))
            self.assertEqual(root.find(".//{*}pgSz").get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}orient"), "landscape")
            self.assertIsNotNone(root.find(".//{*}pgMar")); self.assertIsNotNone(root.find(".//{*}pStyle")); self.assertIsNotNone(root.find(".//{*}b"))
            for name, digest in hashes.items(): self.assertEqual(hashlib.sha256(package.read(name)).digest(), digest)
        self.session.refresh_from_db(); self.assertEqual(self.session.status, "complete")

    def test_cross_user_cannot_generate(self):
        with self.assertRaises(DocumentProcessingSession.DoesNotExist): generate_session(self.session.id, self.other)

    def test_one_time_download_cleans_after_close(self):
        generate_session(self.session.id, self.user); self.client.force_login(self.user)
        response = self.client.get(reverse("abbreviation_tool:download", args=[self.session.id])); self.assertEqual(response.status_code, 200); self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        b"".join(response.streaming_content); response.close(); self.session.refresh_from_db()
        self.assertIsNotNone(self.session.deleted_at); self.assertFalse(session_directory(self.session.id).exists())
        self.assertEqual(self.client.get(reverse("abbreviation_tool:download", args=[self.session.id])).status_code, 404)

    def test_pending_ambiguity_blocks_generation(self):
        item = self.session.suggestions.first(); item.ambiguity_status = "ambiguous"; item.review_status = "pending"; item.save(update_fields=("ambiguity_status", "review_status"))
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError): generate_session(self.session.id, self.user)
