import re
import unicodedata
from dataclasses import dataclass

from abbreviation_tool.models import AbbreviationEntry, AbbreviationVariant, DocumentProcessingSession


POLICY_ALL = "all"
POLICY_KEEP_FIRST = "keep_first"
POLICY_DEFINE_FIRST = "define_first"
POLICIES = (POLICY_ALL, POLICY_KEEP_FIRST, POLICY_DEFINE_FIRST)


@dataclass(frozen=True)
class Match:
    entry: AbbreviationEntry
    original: str
    proposed: str
    start: int
    end: int
    confidence: float
    ambiguity: str
    mixed_format: bool


@dataclass(frozen=True)
class Candidate:
    entry: AbbreviationEntry
    phrase: str
    is_variant: bool = False
    case_sensitive: bool = False


EXCLUDED_PATTERNS = (
    re.compile(r"https?://\S+|www\.\S+", re.I),
    re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"),
    re.compile(r"(?:[A-Za-z]:\\|/)[^\s]+"),
    re.compile(r"\b(?:REF|NO|SERIAL|SN)[:#-]?\s*[A-Z0-9/-]+\b", re.I),
)


def normalize(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def phrase_pattern(phrase, case_sensitive=False):
    escaped = re.escape(phrase).replace(r"\ ", r"[ \u00a0]+")
    return re.compile(rf"(?<![\w]){escaped}(?![\w])", 0 if case_sensitive else re.I)


def excluded_ranges(text):
    return [(match.start(), match.end()) for pattern in EXCLUDED_PATTERNS for match in pattern.finditer(text)]


def overlaps(start, end, ranges):
    return any(start < range_end and end > range_start for range_start, range_end in ranges)


def profile_entries(profile):
    entries = AbbreviationEntry.objects.filter(status=AbbreviationEntry.Status.ACTIVE)
    if profile:
        selected = entries.filter(profiles=profile)
        if selected.exists():
            entries = selected
        entries = entries.exclude(excluded_from_profiles=profile)
    return entries.select_related("category").prefetch_related("variants", "preferred_in_profiles")


def candidates_for(profile, operation, force_case_sensitive=False):
    candidates = []
    for entry in profile_entries(profile):
        phrase = entry.full_form if operation == DocumentProcessingSession.Operation.ABBREVIATE else entry.abbreviation
        candidates.append(Candidate(entry, phrase, False, force_case_sensitive or entry.case_sensitive))
        variant_type = AbbreviationVariant.VariantType.FULL_FORM if operation == DocumentProcessingSession.Operation.ABBREVIATE else AbbreviationVariant.VariantType.ABBREVIATION
        for variant in entry.variants.all():
            if variant.status == AbbreviationEntry.Status.ACTIVE and variant.variant_type in {variant_type, AbbreviationVariant.VariantType.PLURAL, AbbreviationVariant.VariantType.POSSESSIVE, AbbreviationVariant.VariantType.HYPHENATED, AbbreviationVariant.VariantType.SPELLING}:
                candidates.append(Candidate(entry, variant.variant, True, force_case_sensitive or variant.case_sensitive))
    return sorted(candidates, key=lambda item: (-len(item.phrase), -item.entry.is_preferred, -item.entry.priority, item.entry.pk))


def existing_definition_ranges(text):
    return [(match.start(), match.end()) for match in re.finditer(r"\b[^()]{2,100}\s+\([A-Z][A-Z0-9&/ .-]{1,30}\)", text)]


def find_matches(container, candidates, operation, policy=POLICY_DEFINE_FIRST, seen=None):
    seen = seen if seen is not None else set()
    occupied = []
    results = []
    excluded = excluded_ranges(container.text) + existing_definition_ranges(container.text)
    meanings = {}
    for candidate in candidates:
        meanings.setdefault(candidate.entry.normalized_abbreviation, set()).add(candidate.entry.normalized_full_form)
    for candidate in candidates:
        for found in phrase_pattern(candidate.phrase, candidate.case_sensitive).finditer(container.text):
            start, end = found.span()
            if overlaps(start, end, excluded) or overlaps(start, end, occupied):
                continue
            entry = candidate.entry
            identity = entry.normalized_full_form
            ambiguous = len(meanings.get(entry.normalized_abbreviation, ())) > 1 or entry.is_ambiguous
            if operation == DocumentProcessingSession.Operation.ABBREVIATE:
                first = identity not in seen
                if policy == POLICY_KEEP_FIRST and first:
                    seen.add(identity)
                    occupied.append((start, end))
                    continue
                proposed = f"{found.group(0)} ({entry.abbreviation})" if policy == POLICY_DEFINE_FIRST and first else entry.abbreviation
                seen.add(identity)
            else:
                proposed = entry.full_form
            confidence = 100.0 if not candidate.is_variant and not ambiguous else 90.0 if candidate.is_variant and not ambiguous else 60.0
            results.append(Match(entry, found.group(0), proposed, start, end, confidence, "ambiguous" if ambiguous else "unambiguous", container.mixed_format(start, end)))
            occupied.append((start, end))
    return sorted(results, key=lambda item: item.start)
