import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from django.core.cache import cache


API_ROOT = "https://api.dictionaryapi.dev/api/v2/entries/en/"
WORD_PATTERN = re.compile(r"^[A-Za-z][A-Za-z '\-]{0,79}$")


class DictionaryLookupError(Exception):
    pass


def _region(audio_url):
    lowered = audio_url.lower()
    if "-uk." in lowered or "_uk." in lowered or "/uk/" in lowered:
        return "British"
    if "-us." in lowered or "_us." in lowered or "/us/" in lowered:
        return "American"
    return "General"


def lookup_word(word):
    word = " ".join(word.strip().split())
    if not WORD_PATTERN.fullmatch(word):
        raise DictionaryLookupError("Enter an English word or short phrase using letters, spaces, apostrophes, or hyphens.")
    cache_key = f"dictionary:v1:{word.casefold()}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    request = Request(API_ROOT + quote(word), headers={"Accept": "application/json", "User-Agent": "NecessaryTools/1.0"})
    try:
        with urlopen(request, timeout=6) as response:
            payload = json.load(response)
    except HTTPError as exc:
        if exc.code == 404:
            raise DictionaryLookupError(f'No dictionary entry was found for "{word}".') from exc
        raise DictionaryLookupError("The dictionary provider could not complete the lookup.") from exc
    except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise DictionaryLookupError("The dictionary service is temporarily unavailable. Please try again.") from exc
    if not isinstance(payload, list) or not payload:
        raise DictionaryLookupError(f'No dictionary entry was found for "{word}".')
    result = {"word": payload[0].get("word") or word, "phonetic": "", "pronunciations": [], "meanings": [], "source_urls": []}
    seen_pronunciations = set()
    for entry in payload:
        result["phonetic"] = result["phonetic"] or entry.get("phonetic") or ""
        result["source_urls"].extend(url for url in entry.get("sourceUrls", []) if url not in result["source_urls"])
        for phonetic in entry.get("phonetics", []):
            text, audio = phonetic.get("text") or "", phonetic.get("audio") or ""
            key = (text, audio)
            if key in seen_pronunciations or not (text or audio):
                continue
            seen_pronunciations.add(key)
            result["pronunciations"].append({"text": text, "audio": audio, "region": _region(audio)})
        for meaning in entry.get("meanings", []):
            definitions = []
            synonyms = list(meaning.get("synonyms") or [])
            antonyms = list(meaning.get("antonyms") or [])
            for definition in meaning.get("definitions", []):
                if definition.get("definition"):
                    definitions.append({"definition": definition["definition"], "example": definition.get("example") or ""})
                synonyms.extend(definition.get("synonyms") or [])
                antonyms.extend(definition.get("antonyms") or [])
            result["meanings"].append({
                "part_of_speech": meaning.get("partOfSpeech") or "Unspecified",
                "definitions": definitions,
                "synonyms": list(dict.fromkeys(synonyms))[:30],
                "antonyms": list(dict.fromkeys(antonyms))[:30],
            })
    cache.set(cache_key, result, 60 * 60 * 12)
    return result
