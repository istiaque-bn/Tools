from dataclasses import dataclass

from abbreviation_tool.storage import ORIGINAL_NAME, session_directory

from .ooxml import document_containers


@dataclass(frozen=True)
class PreviewSegment:
    text: str
    suggestion_id: str | None = None
    status: str = "plain"


@dataclass(frozen=True)
class PreviewContainer:
    identifier: str
    container_type: str
    segments: list[PreviewSegment]


def build_preview(session):
    suggestions = list(session.suggestions.order_by("container_identifier", "start_offset"))
    by_container = {}
    for suggestion in suggestions:
        by_container.setdefault(suggestion.container_identifier, []).append(suggestion)
    preview = []
    path = session_directory(session.id) / ORIGINAL_NAME
    for container in document_containers(path, include_tables=session.processing_options.get("include_tables", True), include_headers_footers=session.processing_options.get("include_headers_footers", False), include_footnotes_endnotes=session.processing_options.get("include_footnotes_endnotes", False)):
        cursor = 0
        segments = []
        for suggestion in by_container.get(container.identifier, []):
            if suggestion.start_offset > cursor:
                segments.append(PreviewSegment(container.text[cursor:suggestion.start_offset]))
            segments.append(PreviewSegment(
                container.text[suggestion.start_offset:suggestion.end_offset],
                str(suggestion.id),
                "ambiguous" if suggestion.ambiguity_status == "ambiguous" and suggestion.review_status == "pending" else suggestion.review_status,
            ))
            cursor = suggestion.end_offset
        if cursor < len(container.text):
            segments.append(PreviewSegment(container.text[cursor:]))
        preview.append(PreviewContainer(container.identifier, container.container_type, segments))
    return preview
