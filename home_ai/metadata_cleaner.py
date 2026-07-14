import io
import zipfile
from pathlib import Path

import fitz
from lxml import etree
from PIL import Image, ImageOps


MAX_FILE_SIZE = 50 * 1024 * 1024
MAX_UNCOMPRESSED = 250 * 1024 * 1024
OFFICE_EXTENSIONS = {".docx", ".pptx"}


def _clean_pdf(data):
    try:
        document = fitz.open(stream=data, filetype="pdf")
        if document.needs_pass:
            raise ValueError("Password-protected PDFs cannot be cleaned.")
        document.set_metadata({})
        if document.xref_xml_metadata():
            document.del_xml_metadata()
        for page in document:
            annotation = page.first_annot
            while annotation:
                following = annotation.next
                page.delete_annot(annotation)
                annotation = following
        output = io.BytesIO(document.tobytes(garbage=4, clean=True, deflate=True))
        document.close()
        return output
    except fitz.FileDataError as exc:
        raise ValueError("The PDF is invalid or damaged.") from exc


def _clean_xml(name, data, removed_parts, extension):
    parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=False)
    try:
        root = etree.fromstring(data, parser)
    except etree.XMLSyntaxError:
        return data
    for relationship in root.xpath("//*[local-name()='Relationship']"):
        target = (relationship.get("Target") or "").lower()
        if (
            "docprops/" in target
            or "comment" in target
            or any(
                part.lower().endswith(target.lstrip("../")) for part in removed_parts
            )
        ):
            relationship.getparent().remove(relationship)
    for override in root.xpath("//*[local-name()='Override']"):
        part = (override.get("PartName") or "").lstrip("/")
        if part in removed_parts:
            override.getparent().remove(override)
    if extension == ".docx":
        for node in root.xpath(
            "//*[local-name()='commentRangeStart' or local-name()='commentRangeEnd' or local-name()='commentReference' or local-name()='del' or local-name()='trackRevisions']"
        ):
            node.getparent().remove(node)
        for node in root.xpath("//*[local-name()='ins']"):
            parent = node.getparent()
            position = parent.index(node)
            for child in list(node):
                parent.insert(position, child)
                position += 1
            parent.remove(node)
    for node in root.iter():
        for attribute in list(node.attrib):
            if etree.QName(attribute).localname in {
                "author",
                "date",
                "initials",
                "lastEditedBy",
            }:
                del node.attrib[attribute]
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=None)


def _clean_office(data, extension):
    try:
        source = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValueError("The Office document is invalid or damaged.") from exc
    infos = source.infolist()
    if len(infos) > 5000 or sum(item.file_size for item in infos) > MAX_UNCOMPRESSED:
        source.close()
        raise ValueError(
            "The Office document expands beyond the safe processing limit."
        )
    removed = {
        item.filename
        for item in infos
        if item.filename.startswith("docProps/")
        or "comment" in item.filename.lower()
        or item.filename.startswith("word/people")
    }
    output = io.BytesIO()
    with source, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as destination:
        for item in infos:
            if item.filename in removed or item.is_dir():
                continue
            content = source.read(item)
            if item.filename.endswith((".xml", ".rels")):
                content = _clean_xml(item.filename, content, removed, extension)
            destination.writestr(item, content)
    output.seek(0)
    return output


def _clean_image(data, extension):
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
        image = ImageOps.exif_transpose(image)
    except OSError as exc:
        raise ValueError("The image is invalid or unsupported.") from exc
    formats = {
        ".jpg": "JPEG",
        ".jpeg": "JPEG",
        ".png": "PNG",
        ".webp": "WEBP",
        ".tif": "TIFF",
        ".tiff": "TIFF",
    }
    output = io.BytesIO()
    if formats[extension] == "JPEG" and image.mode not in {"RGB", "L"}:
        image = image.convert("RGB")
    image.save(output, formats[extension])
    output.seek(0)
    return output


def clean_metadata(upload):
    if not upload or upload.size < 1 or upload.size > MAX_FILE_SIZE:
        raise ValueError("Choose a supported file no larger than 50 MB.")
    extension = Path(upload.name).suffix.lower()
    supported = {
        ".pdf",
        ".docx",
        ".pptx",
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".tif",
        ".tiff",
    }
    if extension not in supported:
        raise ValueError("Use PDF, DOCX, PPTX, JPG, PNG, WebP, or TIFF.")
    data = upload.read()
    upload.seek(0)
    if extension == ".pdf":
        output = _clean_pdf(data)
    elif extension in OFFICE_EXTENSIONS:
        output = _clean_office(data, extension)
    else:
        output = _clean_image(data, extension)
    return output, f"{Path(upload.name).stem[:100] or 'document'}-clean{extension}"
