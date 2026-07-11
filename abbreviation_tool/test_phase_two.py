import tempfile
import zipfile
from datetime import timedelta
from io import BytesIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import AbbreviationProfile, DocumentProcessingSession
from .storage import cleanup_expired, session_directory
from .validators import DOCX_MIME, validate_docx


CONTENT_TYPES = b'''<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'''
RELS = b'''<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"></Relationships>'''
DOCUMENT = b'''<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Test</w:t></w:r></w:p></w:body></w:document>'''


def docx_upload(name="document.docx", additions=None, content_type=DOCX_MIME):
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", CONTENT_TYPES)
        package.writestr("_rels/.rels", RELS)
        package.writestr("word/document.xml", DOCUMENT)
        for member, value in (additions or {}).items():
            package.writestr(member, value)
    return SimpleUploadedFile(name, output.getvalue(), content_type=content_type)


@override_settings(DOCX_ABBREVIATION_MAX_UPLOAD_MB=2, DOCX_ABBREVIATION_MAX_UNCOMPRESSED_MB=5, DOCX_ABBREVIATION_MAX_ZIP_RATIO=100, DOCX_ABBREVIATION_MAX_ZIP_MEMBERS=100)
class DocxValidationTests(TestCase):
    def test_valid_docx(self):
        self.assertEqual(validate_docx(docx_upload()).member_count, 3)

    def test_rejects_wrong_extension_and_fake_docx(self):
        with self.assertRaises(ValidationError):
            validate_docx(docx_upload("document.pdf"))
        with self.assertRaises(ValidationError):
            validate_docx(SimpleUploadedFile("fake.docx", b"not a zip", content_type=DOCX_MIME))

    def test_rejects_macro_and_path_traversal(self):
        with self.assertRaises(ValidationError):
            validate_docx(docx_upload(additions={"word/vbaProject.bin": b"macro"}))
        with self.assertRaises(ValidationError):
            validate_docx(docx_upload(additions={"../escape.xml": b"unsafe"}))

    def test_rejects_external_relationship(self):
        external = b'''<Relationships><Relationship TargetMode="External" Target="https://example.com"/></Relationships>'''
        with self.assertRaises(ValidationError):
            validate_docx(docx_upload(additions={"word/_rels/document.xml.rels": external}))


class SecureSessionTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.override = override_settings(DOCX_ABBREVIATION_TEMP_ROOT=self.temp.name, DOCX_ABBREVIATION_MAX_UPLOAD_MB=2, DOCX_ABBREVIATION_MAX_UNCOMPRESSED_MB=5, DOCX_ABBREVIATION_MAX_ZIP_RATIO=100, DOCX_ABBREVIATION_MAX_ZIP_MEMBERS=100)
        self.override.enable()
        self.user = get_user_model().objects.create_user("session-user", password="test-password")
        self.other = get_user_model().objects.create_user("other-user", password="test-password")
        self.user.groups.add(Group.objects.get(name="DOCX Abbreviation Users"))
        self.other.groups.add(Group.objects.get(name="DOCX Abbreviation Users"))
        self.profile = AbbreviationProfile.objects.get(name="General")
        self.client.force_login(self.user)

    def tearDown(self):
        self.override.disable()
        self.temp.cleanup()

    def create_session(self):
        response = self.client.post(reverse("abbreviation_tool:upload"), {
            "operation_type": "abbreviate", "profile": self.profile.id,
            "replacement_policy": "define_first", "include_tables": "on",
            "pdf_file": docx_upload(),
        })
        self.assertEqual(response.status_code, 302)
        return DocumentProcessingSession.objects.latest("created_at")

    def test_upload_creates_private_owned_session(self):
        session = self.create_session()
        path = session_directory(session.id) / "original.docx"
        self.assertTrue(path.exists())
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)

    def test_cross_user_access_is_not_found(self):
        session = self.create_session()
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("abbreviation_tool:session", args=[session.id])).status_code, 404)

    def test_cancel_deletes_files_and_marks_session(self):
        session = self.create_session()
        response = self.client.post(reverse("abbreviation_tool:cancel", args=[session.id]))
        self.assertEqual(response.status_code, 302)
        session.refresh_from_db()
        self.assertFalse(session_directory(session.id).exists())
        self.assertIsNotNone(session.deleted_at)

    def test_cleanup_deletes_expired_session(self):
        session = self.create_session()
        session.expires_at = timezone.now() - timedelta(seconds=1)
        session.save(update_fields=("expires_at",))
        self.assertEqual(cleanup_expired(), 1)
        self.assertFalse(session_directory(session.id).exists())

    def test_logout_deletes_active_session(self):
        session = self.create_session()
        self.client.post(reverse("logout"))
        session.refresh_from_db()
        self.assertIsNotNone(session.deleted_at)
        self.assertFalse(session_directory(session.id).exists())
