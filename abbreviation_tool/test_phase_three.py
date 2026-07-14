import tempfile
import zipfile
from datetime import timedelta
from io import BytesIO

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from .models import (
    AbbreviationEntry,
    AbbreviationProfile,
    AbbreviationVariant,
    DocumentProcessingSession,
)
from .services.analysis import analyse_session
from .services.matching import (
    POLICY_ALL,
    POLICY_DEFINE_FIRST,
    POLICY_KEEP_FIRST,
    candidates_for,
    find_matches,
)
from .services.ooxml import CharacterLocation, TextContainer, document_containers
from .storage import save_original
from .test_phase_two import CONTENT_TYPES, DOCX_MIME, RELS


def container(text, styles=None):
    styles = styles or [b""] * len(text)
    mapping = [CharacterLocation(index, 0, styles[index]) for index in range(len(text))]
    return TextContainer("word/document.xml", "p1", "paragraph", text, mapping)


class MatchingEngineTests(TestCase):
    def setUp(self):
        self.profile = AbbreviationProfile.objects.get(name="General")

    def entry(self, abbreviation, full_form, **kwargs):
        entry = AbbreviationEntry.objects.create(
            abbreviation=abbreviation, full_form=full_form, **kwargs
        )
        entry.profiles.add(self.profile)
        return entry

    def test_longest_match_first_and_whole_words(self):
        short = self.entry("AF", "Armed Forces")
        long = self.entry("BAF", "Bangladesh Armed Forces", priority=2)
        matches = find_matches(
            container(
                "Bangladesh Armed Forces and Armed Forces, not Armed ForcesCommander."
            ),
            candidates_for(self.profile, "abbreviate"),
            "abbreviate",
            POLICY_ALL,
        )
        self.assertEqual(
            [(m.entry, m.original) for m in matches],
            [(long, "Bangladesh Armed Forces"), (short, "Armed Forces")],
        )

    def test_first_use_policies(self):
        self.entry("HQ", "Headquarters")
        candidates = candidates_for(self.profile, "abbreviate")
        text = container("Headquarters then Headquarters.")
        defined = find_matches(text, candidates, "abbreviate", POLICY_DEFINE_FIRST)
        self.assertEqual([m.proposed for m in defined], ["Headquarters (HQ)", "HQ"])
        kept = find_matches(text, candidates, "abbreviate", POLICY_KEEP_FIRST)
        self.assertEqual([m.proposed for m in kept], ["HQ"])

    def test_case_punctuation_and_variant(self):
        entry = self.entry("CO", "Commanding Officer", case_sensitive=True)
        AbbreviationVariant.objects.create(
            entry=entry, variant="Commanding Officers", variant_type="plural"
        )
        matches = find_matches(
            container("Commanding Officer, commanding officer; Commanding Officers."),
            candidates_for(self.profile, "abbreviate"),
            "abbreviate",
            POLICY_ALL,
        )
        self.assertEqual(
            [m.original for m in matches], ["Commanding Officer", "Commanding Officers"]
        )

    def test_urls_emails_and_existing_definitions_are_excluded(self):
        self.entry("HQ", "Headquarters")
        text = container("Headquarters (HQ) https://HQ.example user@HQ.com HQ")
        matches = find_matches(
            text,
            candidates_for(self.profile, "deabbreviate"),
            "deabbreviate",
            POLICY_ALL,
        )
        self.assertEqual([m.original for m in matches], ["HQ"])

    def test_ambiguous_expansion_is_flagged(self):
        first = self.entry(
            "CO", "Commanding Officer", is_ambiguous=True, is_preferred=True
        )
        self.entry("CO", "Company", is_ambiguous=True)
        matches = find_matches(
            container("CO"),
            candidates_for(self.profile, "deabbreviate"),
            "deabbreviate",
            POLICY_ALL,
        )
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].entry, first)
        self.assertEqual(matches[0].ambiguity, "ambiguous")
        self.assertEqual(matches[0].confidence, 60.0)

    def test_cross_run_mixed_format_detection(self):
        self.entry("BAF", "Bangladesh Armed Forces")
        text = "Bangladesh Armed Forces"
        styles = [b"normal"] * 11 + [b"bold"] * (len(text) - 11)
        matches = find_matches(
            container(text, styles),
            candidates_for(self.profile, "abbreviate"),
            "abbreviate",
            POLICY_ALL,
        )
        self.assertTrue(matches[0].mixed_format)


class AnalysisIntegrationTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.override = override_settings(DOCX_ABBREVIATION_TEMP_ROOT=self.temp.name)
        self.override.enable()
        self.user = get_user_model().objects.create_user("analysis-user")
        self.profile = AbbreviationProfile.objects.get(name="General")
        entry = AbbreviationEntry.objects.create(
            abbreviation="BAF", full_form="Bangladesh Armed Forces"
        )
        entry.profiles.add(self.profile)

    def tearDown(self):
        self.override.disable()
        self.temp.cleanup()

    def cross_run_upload(self):
        document = b"""<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:rPr><w:b/></w:rPr><w:t>Bangladesh </w:t></w:r><w:r><w:t>Armed Forces</w:t></w:r></w:p></w:body></w:document>"""
        output = BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as package:
            package.writestr("[Content_Types].xml", CONTENT_TYPES)
            package.writestr("_rels/.rels", RELS)
            package.writestr("word/document.xml", document)
        from django.core.files.uploadedfile import SimpleUploadedFile

        return SimpleUploadedFile(
            "cross-run.docx", output.getvalue(), content_type=DOCX_MIME
        )

    def test_ooxml_mapping_and_persisted_analysis(self):
        upload = self.cross_run_upload()
        session = DocumentProcessingSession.objects.create(
            user=self.user,
            original_filename="test.docx",
            operation_type="abbreviate",
            profile=self.profile,
            file_size=upload.size,
            expires_at=timezone.now() + timedelta(minutes=30),
        )
        save_original(session, upload)
        containers = document_containers(
            self.temp.name + "/" + str(session.id) + "/original.docx"
        )
        self.assertEqual(containers[0].text, "Bangladesh Armed Forces")
        analyse_session(session, policy=POLICY_ALL)
        session.refresh_from_db()
        suggestion = session.suggestions.get()
        self.assertEqual(suggestion.proposed_text, "BAF")
        self.assertTrue(suggestion.mixed_format_warning)
        self.assertEqual(session.status, "review")
