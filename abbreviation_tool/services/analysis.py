from time import monotonic

from django.conf import settings
from django.core.exceptions import ValidationError

from abbreviation_tool.models import DocumentProcessingSession, ProcessingSuggestion
from abbreviation_tool.storage import ORIGINAL_NAME, session_directory

from .matching import candidates_for, find_matches
from .ooxml import document_containers


def analyse_session(session, policy="define_first", include_tables=True):
    session.status = DocumentProcessingSession.Status.ANALYSING
    session.save(update_fields=("status",))
    session.suggestions.all().delete()
    try:
        started = monotonic()
        candidates = candidates_for(session.profile, session.operation_type, session.processing_options.get("case_sensitive", False))
        containers = document_containers(
            session_directory(session.id) / ORIGINAL_NAME,
            include_tables=include_tables,
            include_headers_footers=session.processing_options.get("include_headers_footers", False),
            include_footnotes_endnotes=session.processing_options.get("include_footnotes_endnotes", False),
        )
        suggestions = []
        seen = set()
        for container in containers:
            for match in find_matches(container, candidates, session.operation_type, policy=policy, seen=seen):
                if monotonic() - started > settings.DOCX_ABBREVIATION_ANALYSIS_TIMEOUT_SECONDS:
                    raise ValidationError("Document analysis exceeded the configured time limit.")
                if session.processing_options.get("high_confidence_only") and match.confidence < 90:
                    continue
                if len(suggestions) >= settings.DOCX_ABBREVIATION_MAX_SUGGESTIONS:
                    raise ValidationError("The document produced more suggestions than the configured safe limit.")
                suggestions.append(ProcessingSuggestion(
                    session=session,
                    abbreviation_entry=match.entry,
                    operation_type=session.operation_type,
                    original_text=match.original,
                    proposed_text=match.proposed,
                    container_type=container.container_type,
                    container_identifier=container.identifier,
                    paragraph_identifier=container.identifier,
                    start_offset=match.start,
                    end_offset=match.end,
                    confidence=match.confidence,
                    ambiguity_status=match.ambiguity,
                    mixed_format_warning=match.mixed_format,
                ))
        ProcessingSuggestion.objects.bulk_create(suggestions)
        session.suggestion_count = len(suggestions)
        session.ambiguous_count = sum(item.ambiguity_status == "ambiguous" for item in suggestions)
        session.status = DocumentProcessingSession.Status.REVIEW
        session.save(update_fields=("suggestion_count", "ambiguous_count", "status"))
        return suggestions
    except Exception:
        session.suggestions.all().delete()
        DocumentProcessingSession.objects.filter(id=session.id).update(status=DocumentProcessingSession.Status.FAILED)
        raise
