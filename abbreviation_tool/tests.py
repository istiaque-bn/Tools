from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import AbbreviationEntry, AbbreviationProfile


class AbbreviationToolPhaseOneTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        AbbreviationEntry.objects.create(abbreviation="SITREP", full_form="Situation Report", source_name="JSSDM 2022")
        AbbreviationEntry.objects.create(abbreviation="AA", full_form="Avenue of Approach", is_ambiguous=True)
        AbbreviationEntry.objects.create(abbreviation="AA", full_form="Anti-Aircraft", is_ambiguous=True)

    def setUp(self):
        self.user = get_user_model().objects.create_user("docx-user", password="test-password")

    def grant_standard_access(self):
        self.user.groups.add(Group.objects.get(name="DOCX Abbreviation Users"))
        self.user = get_user_model().objects.get(pk=self.user.pk)

    def test_landing_requires_authentication(self):
        response = self.client.get(reverse("abbreviation_tool:landing"))
        self.assertEqual(response.status_code, 302)

    def test_all_authenticated_users_receive_checker_permission(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("abbreviation_tool:landing")).status_code, 200)

    @override_settings(DOCX_ABBREVIATION_TOOL_ENABLED=False)
    def test_feature_flag_disables_route(self):
        self.grant_standard_access()
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("abbreviation_tool:landing")).status_code, 404)

    def test_dictionary_search_uses_imported_jssdm_data(self):
        self.grant_standard_access()
        self.client.force_login(self.user)
        response = self.client.get(reverse("abbreviation_tool:dictionary"), {"q": "Situation Report"})
        self.assertContains(response, "SITREP")

    def test_profiles_are_database_driven(self):
        self.assertTrue(AbbreviationProfile.objects.filter(name="General", active=True).exists())
        self.assertTrue(AbbreviationProfile.objects.filter(name="Joint", active=True).exists())

    def test_entry_normalization_and_unique_pair(self):
        first = AbbreviationEntry.objects.create(abbreviation=" TEST ", full_form="  Test   Entry ")
        self.assertEqual(first.normalized_abbreviation, "test")
        self.assertEqual(first.normalized_full_form, "test entry")
        with self.assertRaises(IntegrityError):
            AbbreviationEntry.objects.create(abbreviation="test", full_form="test entry")

    def test_ambiguous_import_is_flagged(self):
        matches = AbbreviationEntry.objects.filter(abbreviation="AA")
        self.assertGreater(matches.count(), 1)
        self.assertFalse(matches.filter(is_ambiguous=False).exists())

    def test_permission_groups_are_configured(self):
        self.assertEqual(Group.objects.get(name="DOCX Abbreviation Users").permissions.count(), 3)
        self.assertEqual(Group.objects.get(name="DOCX Abbreviation Administrators").permissions.count(), 8)
