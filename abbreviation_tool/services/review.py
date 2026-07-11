from copy import deepcopy

from django.core.exceptions import ValidationError
from django.db import transaction

from abbreviation_tool.models import AbbreviationEntry, DocumentProcessingSession, ProcessingSuggestion


MAX_HISTORY = 50


def _snapshot(suggestions):
    return [{
        "id": str(item.id),
        "review_status": item.review_status,
        "user_modified_text": item.user_modified_text,
        "selected_meaning_id": item.selected_meaning_id,
    } for item in suggestions]


def _history(session):
    options = deepcopy(session.processing_options)
    options.setdefault("review_undo", [])
    options.setdefault("review_redo", [])
    return options


def _record(session, suggestions):
    options = _history(session)
    options["review_undo"].append(_snapshot(suggestions))
    options["review_undo"] = options["review_undo"][-MAX_HISTORY:]
    options["review_redo"] = []
    session.processing_options = options


def _restore(snapshot):
    ids = [item["id"] for item in snapshot]
    suggestions = {str(item.id): item for item in ProcessingSuggestion.objects.filter(id__in=ids)}
    changed = []
    for state in snapshot:
        suggestion = suggestions.get(state["id"])
        if suggestion:
            suggestion.review_status = state["review_status"]
            suggestion.user_modified_text = state["user_modified_text"]
            suggestion.selected_meaning_id = state["selected_meaning_id"]
            changed.append(suggestion)
    ProcessingSuggestion.objects.bulk_update(changed, ("review_status", "user_modified_text", "selected_meaning"))


def _update_counts(session):
    session.accepted_count = session.suggestions.filter(review_status__in=("accepted", "edited")).count()
    session.rejected_count = session.suggestions.filter(review_status="rejected").count()
    session.save(update_fields=("accepted_count", "rejected_count", "processing_options"))


@transaction.atomic
def decide(session_id, user, suggestion_id, action, replacement="", selected_meaning_id=None):
    session = DocumentProcessingSession.objects.select_for_update().get(id=session_id, user=user, deleted_at__isnull=True)
    suggestion = session.suggestions.select_for_update().get(id=suggestion_id)
    _record(session, [suggestion])
    if action == "accept":
        if suggestion.ambiguity_status == "ambiguous" and not selected_meaning_id:
            raise ValidationError("Select a meaning before accepting an ambiguous abbreviation.")
        suggestion.review_status = ProcessingSuggestion.ReviewStatus.ACCEPTED
        suggestion.user_modified_text = ""
    elif action == "reject":
        suggestion.review_status = ProcessingSuggestion.ReviewStatus.REJECTED
        suggestion.user_modified_text = ""
    elif action == "edit":
        replacement = " ".join(replacement.split())
        if not replacement or len(replacement) > 500:
            raise ValidationError("Enter a replacement between 1 and 500 characters.")
        suggestion.review_status = ProcessingSuggestion.ReviewStatus.EDITED
        suggestion.user_modified_text = replacement
    elif action == "reset":
        suggestion.review_status = ProcessingSuggestion.ReviewStatus.PENDING
        suggestion.user_modified_text = ""
        suggestion.selected_meaning = None
    else:
        raise ValidationError("Choose a valid review action.")
    if selected_meaning_id:
        selected = AbbreviationEntry.objects.get(id=selected_meaning_id, normalized_abbreviation=suggestion.abbreviation_entry.normalized_abbreviation)
        suggestion.selected_meaning = selected
        suggestion.proposed_text = selected.full_form
    suggestion.save(update_fields=("review_status", "user_modified_text", "selected_meaning", "proposed_text", "updated_at"))
    _update_counts(session)
    return suggestion


@transaction.atomic
def bulk_decide(session_id, user, action, high_confidence=False, suggestion_ids=None):
    session = DocumentProcessingSession.objects.select_for_update().get(id=session_id, user=user, deleted_at__isnull=True)
    queryset = session.suggestions.select_for_update().all()
    if suggestion_ids is not None:
        queryset = queryset.filter(id__in=suggestion_ids)
    if high_confidence:
        queryset = queryset.filter(confidence__gte=90, ambiguity_status="unambiguous")
    suggestions = list(queryset)
    _record(session, suggestions)
    if action == "accept":
        queryset.filter(ambiguity_status="unambiguous").update(review_status="accepted", user_modified_text="")
    elif action == "reject":
        queryset.update(review_status="rejected", user_modified_text="")
    elif action == "reset":
        queryset.update(review_status="pending", user_modified_text="", selected_meaning=None)
    else:
        raise ValidationError("Choose a valid bulk action.")
    _update_counts(session)


@transaction.atomic
def history_action(session_id, user, direction):
    if direction not in {"undo", "redo"}:
        raise ValidationError("Choose undo or redo.")
    session = DocumentProcessingSession.objects.select_for_update().get(id=session_id, user=user, deleted_at__isnull=True)
    options = _history(session)
    source, target = ("review_undo", "review_redo") if direction == "undo" else ("review_redo", "review_undo")
    if not options[source]:
        raise ValidationError(f"Nothing to {direction}.")
    snapshot = options[source].pop()
    current = list(session.suggestions.filter(id__in=[item["id"] for item in snapshot]))
    options[target].append(_snapshot(current))
    _restore(snapshot)
    session.processing_options = options
    _update_counts(session)
