import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from django.core.cache import cache

from .models import DictionaryEntry


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


def normalise_payload(payload, fallback_word):
    """Convert dictionaryapi.dev-compatible JSON into the local schema."""
    if not isinstance(payload, list) or not payload:
        raise DictionaryLookupError(f'No dictionary entry was found for "{fallback_word}".')
    result = {"word": payload[0].get("word") or fallback_word, "phonetic": "", "pronunciations": [], "meanings": [], "source_urls": []}
    seen = set()
    for entry in payload:
        result["phonetic"] = result["phonetic"] or entry.get("phonetic") or ""
        result["source_urls"].extend(url for url in entry.get("sourceUrls", []) if url not in result["source_urls"])
        for phonetic in entry.get("phonetics", []):
            text, audio = phonetic.get("text") or "", phonetic.get("audio") or ""
            key = (text, audio)
            if key in seen or not (text or audio):
                continue
            seen.add(key)
            result["pronunciations"].append({"text": text, "audio": audio, "region": _region(audio)})
        for meaning in entry.get("meanings", []):
            definitions, synonyms, antonyms = [], list(meaning.get("synonyms") or []), list(meaning.get("antonyms") or [])
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
    return result


def _fetch_online(word, timeout=4):
    request = Request(API_ROOT + quote(word), headers={"Accept": "application/json", "User-Agent": "NecessaryTools/1.0"})
    with urlopen(request, timeout=timeout) as response:
        return normalise_payload(json.load(response), word)


def save_offline(result):
    """Persist text and phonetics, excluding large/remote audio resources."""
    pronunciations = [{**item, "audio": ""} for item in result["pronunciations"]]
    entry, _ = DictionaryEntry.objects.update_or_create(
        word=result["word"].casefold(),
        defaults={"phonetic": result["phonetic"], "pronunciations": pronunciations,
                  "meanings": result["meanings"], "source_urls": result["source_urls"]},
    )
    return entry


def _local_result(entry):
    return {"word": entry.word, "phonetic": entry.phonetic, "pronunciations": entry.pronunciations,
            "meanings": entry.meanings, "source_urls": entry.source_urls, "offline": True, "audio_online": False}


def lookup_word(word):
    word = " ".join(word.strip().split())
    if not WORD_PATTERN.fullmatch(word):
        raise DictionaryLookupError("Enter an English word or short phrase using letters, spaces, apostrophes, or hyphens.")
    cache_key = f"dictionary:v2:{word.casefold()}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    local = DictionaryEntry.objects.filter(word__iexact=word).first()
    if local:
        result = _local_result(local)
        try:
            online = _fetch_online(word, timeout=2)
            audio = [item for item in online["pronunciations"] if item.get("audio")]
            if audio:
                result["pronunciations"] = audio
                result["audio_online"] = True
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError, DictionaryLookupError):
            pass
        # Do not cache an offline miss: audio should appear on the next lookup
        # as soon as connectivity returns.
        if result["audio_online"]:
            cache.set(cache_key, result, 60 * 60 * 12)
        return result

    try:
        result = _fetch_online(word)
    except HTTPError as exc:
        if exc.code == 404:
            raise DictionaryLookupError(f'No offline entry was found for "{word}", and no online entry is available.') from exc
        raise DictionaryLookupError(f'No offline entry was found for "{word}". Connect to the internet and try again.') from exc
    except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise DictionaryLookupError(f'No offline entry was found for "{word}". Connect to the internet and try again.') from exc
    save_offline(result)
    result["offline"] = False
    result["audio_online"] = any(item.get("audio") for item in result["pronunciations"])
    cache.set(cache_key, result, 60 * 60 * 12)
    return result
