import tempfile
import zipfile
from datetime import timedelta
from io import BytesIO
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from lxml import etree
from .models import AbbreviationEntry, AbbreviationProfile, DocumentProcessingSession
from .services.analysis import analyse_session
from .services.generation import generate_session, insert_glossary
from .services.matching import POLICY_ALL
from .storage import save_original
from .test_phase_two import CONTENT_TYPES, DOCX_MIME, RELS


WNS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
BODY = f'''<w:document xmlns:w="{WNS}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><w:body><w:p><w:hyperlink r:id="rId5"><w:r><w:t>Headquarters</w:t></w:r></w:hyperlink></w:p><w:p><w:sdt><w:sdtContent><w:r><w:t>Commanding Officer</w:t></w:r></w:sdtContent></w:sdt></w:p><w:p><w:bookmarkStart w:id="7" w:name="GlossaryHere"/><w:bookmarkEnd w:id="7"/></w:p><w:sectPr><w:pgMar w:top="720"/></w:sectPr></w:body></w:document>'''.encode()
HEADER = f'''<w:hdr xmlns:w="{WNS}"><w:p><w:r><w:t>Headquarters</w:t></w:r></w:p></w:hdr>'''.encode()
FOOTER = f'''<w:ftr xmlns:w="{WNS}"><w:p><w:r><w:t>Commanding Officer</w:t></w:r></w:p></w:ftr>'''.encode()
FOOTNOTES = f'''<w:footnotes xmlns:w="{WNS}"><w:footnote w:id="1"><w:p><w:r><w:t>Headquarters</w:t></w:r></w:p></w:footnote></w:footnotes>'''.encode()
ENDNOTES = f'''<w:endnotes xmlns:w="{WNS}"><w:endnote w:id="1"><w:p><w:r><w:t>Commanding Officer</w:t></w:r></w:p></w:endnote></w:endnotes>'''.encode()


def advanced_docx():
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", CONTENT_TYPES)
        package.writestr("_rels/.rels", RELS)
        package.writestr("word/document.xml", BODY)
        package.writestr("word/header1.xml", HEADER)
        package.writestr("word/footer1.xml", FOOTER)
        package.writestr("word/footnotes.xml", FOOTNOTES)
        package.writestr("word/endnotes.xml", ENDNOTES)
    return SimpleUploadedFile(
        "advanced.docx", output.getvalue(), content_type=DOCX_MIME
    )


class AdvancedStructureTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.override = override_settings(DOCX_ABBREVIATION_TEMP_ROOT=self.temp.name)
        self.override.enable()
        self.user = get_user_model().objects.create_user("advanced-user")
        self.profile = AbbreviationProfile.objects.get(name="General")
        for abbreviation, full_form in (
            ("HQ", "Headquarters"),
            ("CO", "Commanding Officer"),
        ):
            entry = AbbreviationEntry.objects.create(
                abbreviation=abbreviation, full_form=full_form
            )
            entry.profiles.add(self.profile)

    def tearDown(self):
        self.override.disable()
        self.temp.cleanup()

    def session(self, options):
        upload = advanced_docx()
        session = DocumentProcessingSession.objects.create(
            user=self.user,
            original_filename="advanced.docx",
            operation_type="abbreviate",
            profile=self.profile,
            file_size=upload.size,
            processing_options=options,
            expires_at=timezone.now() + timedelta(minutes=30),
        )
        save_original(session, upload)
        return session

    def test_analysis_includes_selected_advanced_parts(self):
        session = self.session(
            {
                "include_tables": True,
                "include_headers_footers": True,
                "include_footnotes_endnotes": True,
            }
        )
        analyse_session(session, POLICY_ALL)
        types = set(session.suggestions.values_list("container_type", flat=True))
        self.assertTrue(
            {"paragraph", "header", "footer", "footnote", "endnote"}.issubset(types)
        )
        self.assertTrue(
            session.suggestions.filter(
                container_identifier__startswith="word/document.xml"
            ).exists()
        )

    def test_generation_modifies_header_and_preserves_other_parts(self):
        session = self.session(
            {
                "include_headers_footers": True,
                "include_footnotes_endnotes": False,
                "glossary_mode": "none",
            }
        )
        analyse_session(session, POLICY_ALL)
        session.suggestions.filter(container_type="header").update(
            review_status="accepted"
        )
        session.suggestions.exclude(container_type="header").update(
            review_status="rejected"
        )
        output = generate_session(session.id, self.user)
        with zipfile.ZipFile(output) as package:
            self.assertIn(b">HQ<", package.read("word/header1.xml"))
            self.assertEqual(package.read("word/footer1.xml"), FOOTER)
            self.assertEqual(package.read("word/footnotes.xml"), FOOTNOTES)

    def test_glossary_insertion_before_section_and_at_bookmark(self):
        inserted = insert_glossary(
            BODY, [("CO", "Commanding Officer"), ("HQ", "Headquarters")]
        )
        root = etree.fromstring(inserted)
        body = root.find(f"{{{WNS}}}body")
        self.assertEqual(body[-1].tag, f"{{{WNS}}}sectPr")
        self.assertEqual(len(root.findall(".//{*}tbl")), 1)
        bookmarked = insert_glossary(BODY, [("HQ", "Headquarters")], "GlossaryHere")
        self.assertEqual(len(etree.fromstring(bookmarked).findall(".//{*}tbl")), 1)
