import os
import zipfile

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from lxml import etree

from abbreviation_tool.models import DocumentProcessingSession, ProcessingSuggestion
from abbreviation_tool.storage import ORIGINAL_NAME, PROCESSED_NAME, session_directory


W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


def _visible_mapping(paragraph):
    text = []
    mapping = []
    for node in paragraph.iter():
        if node.tag == f"{W}t" and node.text:
            for offset, character in enumerate(node.text):
                text.append(character)
                mapping.append((node, offset))
        elif node.tag == f"{W}tab":
            text.append("\t")
            mapping.append((None, 0))
        elif node.tag in {f"{W}br", f"{W}cr"}:
            text.append("\n")
            mapping.append((None, 0))
    return "".join(text), mapping


def _preserve_spaces(node):
    value = node.text or ""
    if value.startswith(" ") or value.endswith(" ") or "  " in value:
        node.set(XML_SPACE, "preserve")


def replace_range(paragraph, start, end, replacement, expected):
    visible, mapping = _visible_mapping(paragraph)
    if (
        start < 0
        or end > len(mapping)
        or start >= end
        or visible[start:end] != expected
    ):
        raise ValidationError(
            "The document structure no longer matches its analysed suggestion offsets."
        )
    selected = mapping[start:end]
    if any(node is None for node, _ in selected):
        raise ValidationError(
            "A replacement crosses an unsupported line break or tab boundary."
        )
    start_node, start_offset = selected[0]
    end_node, end_offset = selected[-1]
    if start_node is end_node:
        original = start_node.text or ""
        start_node.text = (
            original[:start_offset] + replacement + original[end_offset + 1 :]
        )
        _preserve_spaces(start_node)
        return
    start_text = start_node.text or ""
    end_text = end_node.text or ""
    start_node.text = start_text[:start_offset] + replacement
    reached_start = False
    for node, _offset in selected:
        if node is start_node:
            reached_start = True
            continue
        if not reached_start or node is end_node:
            continue
        node.text = ""
    end_node.text = end_text[end_offset + 1 :]
    _preserve_spaces(start_node)
    _preserve_spaces(end_node)


def apply_part_suggestions(xml_bytes, suggestions):
    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        huge_tree=False,
        remove_blank_text=False,
    )
    root = etree.fromstring(xml_bytes, parser)
    paragraphs = list(root.iter(f"{W}p"))
    grouped = {}
    for suggestion in suggestions:
        try:
            index = int(suggestion.paragraph_identifier.rsplit(":p", 1)[1])
        except (ValueError, IndexError) as exc:
            raise ValidationError(
                "A suggestion has an invalid paragraph location."
            ) from exc
        grouped.setdefault(index, []).append(suggestion)
    for index, paragraph_suggestions in grouped.items():
        if index >= len(paragraphs):
            raise ValidationError("A suggestion points outside the document.")
        for suggestion in sorted(
            paragraph_suggestions, key=lambda item: item.start_offset, reverse=True
        ):
            replacement = suggestion.user_modified_text or suggestion.proposed_text
            replace_range(
                paragraphs[index],
                suggestion.start_offset,
                suggestion.end_offset,
                replacement,
                suggestion.original_text,
            )
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=None)


def glossary_rows(session):
    rows = {}
    suggestions = session.suggestions.filter(
        review_status__in=(
            ProcessingSuggestion.ReviewStatus.ACCEPTED,
            ProcessingSuggestion.ReviewStatus.EDITED,
        )
    ).select_related("abbreviation_entry", "selected_meaning")
    for suggestion in suggestions:
        entry = suggestion.selected_meaning or suggestion.abbreviation_entry
        rows[(entry.abbreviation.casefold(), entry.full_form.casefold())] = (
            entry.abbreviation,
            entry.full_form,
        )
    return sorted(rows.values(), key=lambda row: (row[0].casefold(), row[1].casefold()))


def insert_glossary(xml_bytes, rows, bookmark=""):
    if not rows:
        return xml_bytes
    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        huge_tree=False,
        remove_blank_text=False,
    )
    root = etree.fromstring(xml_bytes, parser)
    body = root.find(f"{W}body")
    if body is None:
        raise ValidationError("The document has no body for glossary insertion.")
    heading = etree.Element(f"{W}p")
    heading_properties = etree.SubElement(heading, f"{W}pPr")
    etree.SubElement(heading_properties, f"{W}pStyle").set(f"{W}val", "Heading1")
    heading_run = etree.SubElement(heading, f"{W}r")
    etree.SubElement(heading_run, f"{W}t").text = "Abbreviation Glossary"
    table = etree.Element(f"{W}tbl")
    for abbreviation, full_form in (("Abbreviation", "Full Form"), *rows):
        row = etree.SubElement(table, f"{W}tr")
        for value in (abbreviation, full_form):
            cell = etree.SubElement(row, f"{W}tc")
            paragraph = etree.SubElement(cell, f"{W}p")
            run = etree.SubElement(paragraph, f"{W}r")
            etree.SubElement(run, f"{W}t").text = value
    insertion_index = len(body)
    section = body.find(f"{W}sectPr")
    if section is not None:
        insertion_index = body.index(section)
    if bookmark:
        marker = root.xpath(
            ".//w:bookmarkStart[@w:name=$name]",
            namespaces={"w": W[1:-1]},
            name=bookmark,
        )
        if not marker:
            raise ValidationError(f'The glossary bookmark "{bookmark}" was not found.')
        paragraph = marker[0]
        while paragraph is not None and paragraph.tag != f"{W}p":
            paragraph = paragraph.getparent()
        if paragraph is None or paragraph.getparent() is not body:
            raise ValidationError(
                "The glossary bookmark is not in a supported body paragraph."
            )
        insertion_index = body.index(paragraph) + 1
    body.insert(insertion_index, heading)
    body.insert(insertion_index + 1, table)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8")


def _write_package(original, destination, changed_parts):
    temporary = destination.with_suffix(".tmp")
    try:
        for part, data in changed_parts.items():
            if part.endswith(".xml"):
                etree.fromstring(
                    data, etree.XMLParser(resolve_entities=False, no_network=True)
                )
        with (
            zipfile.ZipFile(original) as source,
            zipfile.ZipFile(temporary, "w") as output,
        ):
            for info in source.infolist():
                data = changed_parts.get(info.filename, source.read(info))
                output.writestr(info, data)
        with zipfile.ZipFile(temporary) as package:
            if "word/document.xml" not in package.namelist():
                raise ValidationError(
                    "Generated DOCX is missing its main document part."
                )
            etree.fromstring(
                package.read("word/document.xml"),
                etree.XMLParser(resolve_entities=False, no_network=True),
            )
            bad = package.testzip()
            if bad:
                raise ValidationError(
                    f"Generated DOCX contains a corrupted package entry: {bad}"
                )
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def generate_session(session_id, user):
    with transaction.atomic():
        session = DocumentProcessingSession.objects.select_for_update().get(
            id=session_id, user=user, deleted_at__isnull=True
        )
        if session.status != DocumentProcessingSession.Status.REVIEW:
            raise ValidationError("This session is not ready to generate.")
        if session.suggestions.filter(
            ambiguity_status="ambiguous", review_status="pending"
        ).exists():
            raise ValidationError(
                "Resolve or reject every ambiguous suggestion before generating the DOCX."
            )
        suggestions = list(
            session.suggestions.filter(
                review_status__in=(
                    ProcessingSuggestion.ReviewStatus.ACCEPTED,
                    ProcessingSuggestion.ReviewStatus.EDITED,
                )
            ).order_by("container_identifier", "-start_offset")
        )
        if not suggestions:
            raise ValidationError(
                "Accept or edit at least one suggestion before generating the DOCX."
            )
        session.status = DocumentProcessingSession.Status.GENERATING
        session.save(update_fields=("status",))
    directory = session_directory(session.id)
    original = directory / ORIGINAL_NAME
    destination = directory / PROCESSED_NAME
    try:
        grouped = {}
        for suggestion in suggestions:
            part = suggestion.container_identifier.rsplit(":p", 1)[0]
            grouped.setdefault(part, []).append(suggestion)
        changed_parts = {}
        with zipfile.ZipFile(original) as package:
            for part, part_suggestions in grouped.items():
                if part not in package.namelist():
                    raise ValidationError(
                        "A suggestion points to a missing OOXML part."
                    )
                changed_parts[part] = apply_part_suggestions(
                    package.read(part), part_suggestions
                )
            mode = session.processing_options.get("glossary_mode", "none")
            if mode in {"insert_end", "bookmark"}:
                main_xml = changed_parts.get(
                    "word/document.xml", package.read("word/document.xml")
                )
                changed_parts["word/document.xml"] = insert_glossary(
                    main_xml,
                    glossary_rows(session),
                    session.processing_options.get("glossary_bookmark", "")
                    if mode == "bookmark"
                    else "",
                )
        _write_package(original, destination, changed_parts)
        session.status = DocumentProcessingSession.Status.COMPLETE
        session.completed_at = timezone.now()
        session.save(update_fields=("status", "completed_at"))
        return destination
    except Exception:
        DocumentProcessingSession.objects.filter(id=session.id).update(
            status=DocumentProcessingSession.Status.FAILED
        )
        raise
