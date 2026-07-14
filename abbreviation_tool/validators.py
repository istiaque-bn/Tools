import re
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath

from django.conf import settings
from django.core.exceptions import ValidationError


DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
REQUIRED_PARTS = {"[Content_Types].xml", "_rels/.rels", "word/document.xml"}
FORBIDDEN_SUFFIXES = {
    ".exe",
    ".dll",
    ".com",
    ".bat",
    ".cmd",
    ".js",
    ".jar",
    ".ps1",
    ".sh",
}
XML_SUFFIXES = {".xml", ".rels"}


@dataclass(frozen=True)
class DocxInspection:
    file_size: int
    member_count: int
    uncompressed_size: int
    unsupported_elements: tuple[str, ...]


def _safe_member(name):
    path = PurePosixPath(name)
    return (
        not path.is_absolute()
        and ".." not in path.parts
        and not re.match(r"^[A-Za-z]:", name)
    )


def validate_docx(upload):
    if not upload:
        raise ValidationError("Choose one DOCX document.")
    if not upload.name.lower().endswith(".docx"):
        raise ValidationError("Only .docx documents are supported.")
    if upload.name.lower().endswith((".docm", ".dotm")):
        raise ValidationError("Macro-enabled documents are not supported.")
    if upload.size < 1:
        raise ValidationError("The DOCX document is empty.")
    declared_type = (getattr(upload, "content_type", "") or "").lower()
    if declared_type and declared_type not in {
        DOCX_MIME,
        "application/zip",
        "application/octet-stream",
    }:
        raise ValidationError("The uploaded MIME type is not a DOCX document.")
    try:
        upload.seek(0)
        with zipfile.ZipFile(upload) as package:
            infos = package.infolist()
            names = {info.filename for info in infos}
            if not REQUIRED_PARTS.issubset(names):
                raise ValidationError("The file is not a valid Word OOXML document.")
            if len(infos) > settings.DOCX_ABBREVIATION_MAX_ZIP_MEMBERS:
                raise ValidationError("The DOCX contains too many package entries.")
            total = sum(info.file_size for info in infos)
            if total > settings.DOCX_ABBREVIATION_MAX_UNCOMPRESSED_MB * 1024 * 1024:
                raise ValidationError(
                    "The expanded DOCX is too large to process safely."
                )
            for info in infos:
                if not _safe_member(info.filename):
                    raise ValidationError("The DOCX contains an unsafe package path.")
                suffix = PurePosixPath(info.filename).suffix.lower()
                if suffix in FORBIDDEN_SUFFIXES:
                    raise ValidationError(
                        "The DOCX contains a forbidden embedded file."
                    )
                if (
                    info.compress_size
                    and info.file_size / info.compress_size
                    > settings.DOCX_ABBREVIATION_MAX_ZIP_RATIO
                ):
                    raise ValidationError(
                        "The DOCX contains a suspicious compression ratio."
                    )
                lower_name = info.filename.lower()
                if "vbaproject" in lower_name or lower_name.endswith(".bin"):
                    raise ValidationError(
                        "Macro or executable OOXML content is not supported."
                    )
                if info.flag_bits & 0x1:
                    raise ValidationError(
                        "Encrypted or password-protected DOCX files are not supported."
                    )
                if suffix in XML_SUFFIXES and info.file_size:
                    content = package.read(info, pwd=None)
                    prefix = content[:2048].upper()
                    if b"<!DOCTYPE" in prefix or b"<!ENTITY" in prefix:
                        raise ValidationError(
                            "Unsafe XML declarations are not supported."
                        )
                    if suffix == ".rels" and re.search(
                        rb'TargetMode\s*=\s*["\']External["\']', content, re.I
                    ):
                        raise ValidationError(
                            "Documents with external relationships are not supported."
                        )
            content_types = package.read("[Content_Types].xml")
            if b"macroEnabled" in content_types or b"vbaProject" in content_types:
                raise ValidationError("Macro-enabled documents are not supported.")
            unsupported = tuple(
                name
                for name in names
                if name.startswith(("word/embeddings/", "word/diagrams/"))
            )
            return DocxInspection(upload.size, len(infos), total, unsupported)
    except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
        raise ValidationError("The DOCX is corrupted or unreadable.") from exc
    finally:
        upload.seek(0)
