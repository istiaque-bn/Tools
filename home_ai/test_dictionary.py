import json
from unittest.mock import patch
from urllib.error import URLError

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, *args):
        return json.dumps(self.payload).encode()


SAMPLE = [
    {
        "word": "hello",
        "phonetic": "/həˈləʊ/",
        "phonetics": [
            {"text": "/həˈləʊ/", "audio": "https://example.test/hello-uk.mp3"},
            {"text": "/həˈloʊ/", "audio": "https://example.test/hello-us.mp3"},
        ],
        "meanings": [
            {
                "partOfSpeech": "exclamation",
                "synonyms": ["greeting"],
                "antonyms": ["goodbye"],
                "definitions": [
                    {"definition": "Used as a greeting.", "example": "Hello, everyone."}
                ],
            }
        ],
        "sourceUrls": ["https://en.wiktionary.org/wiki/hello"],
    }
]


class DictionaryToolTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            "dictionary-user", password="test-password"
        )

    def test_dictionary_requires_login(self):
        response = self.client.get(reverse("dictionary_tool"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    @patch("home_ai.dictionary_provider.urlopen", return_value=FakeResponse(SAMPLE))
    def test_dictionary_displays_complete_provider_data(self, mocked):
        self.client.force_login(self.user)
        response = self.client.get(reverse("dictionary_tool"), {"q": "hello"})
        self.assertEqual(response.status_code, 200)
        for text in (
            "Used as a greeting.",
            "exclamation",
            "/həˈləʊ/",
            "Hello, everyone.",
            "greeting",
            "goodbye",
            "British",
            "American",
        ):
            self.assertContains(response, text)
        mocked.assert_called_once()

    def test_dictionary_rejects_invalid_input_without_network_call(self):
        self.client.force_login(self.user)
        with patch("home_ai.dictionary_provider.urlopen") as mocked:
            response = self.client.get(reverse("dictionary_tool"), {"q": "<script>"})
        self.assertContains(response, "Enter an English word")
        mocked.assert_not_called()

    def test_saved_definition_remains_available_when_audio_provider_is_offline(self):
        self.client.force_login(self.user)
        cache.clear()
        with patch(
            "home_ai.dictionary_provider.urlopen", return_value=FakeResponse(SAMPLE)
        ):
            self.client.get(reverse("dictionary_tool"), {"q": "hello"})
        cache.clear()
        with patch(
            "home_ai.dictionary_provider.urlopen", side_effect=URLError("offline")
        ):
            response = self.client.get(reverse("dictionary_tool"), {"q": "hello"})
        self.assertContains(response, "Used as a greeting.")
        self.assertContains(response, "offline data")
        self.assertContains(
            response, "Pronunciation audio requires an internet connection."
        )
        self.assertNotContains(response, "hello-uk.mp3")

    def test_dashboard_shows_dictionary_card(self):
        self.client.force_login(self.user)
        self.assertContains(
            self.client.get(reverse("home")), reverse("dictionary_tool")
        )
