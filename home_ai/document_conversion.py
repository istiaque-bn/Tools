import shutil
import subprocess
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path


MAX_DOCX_SIZE = 50 * 1024 * 1024


def _libreoffice_binary():
    candidates = (
        "libreoffice",
        "soffice",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        r"C:\Program Files\LibreOffice\program\soffice.exe",
    )
    return next((candidate for candidate in candidates if shutil.which(candidate) or Path(candidate).is_file()), None)


def _validate_docx(upload):
    if not upload or not upload.name.lower().endswith(".docx"):
        raise ValueError("Choose a Word .docx file.")
    if upload.size < 1 or upload.size > MAX_DOCX_SIZE:
        raise ValueError("The DOCX file must be between 1 byte and 50 MB.")
    try:
        upload.seek(0)
        with zipfile.ZipFile(upload) as archive:
            names = set(archive.namelist())
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise ValueError("The uploaded file is not a valid DOCX document.")
    except (zipfile.BadZipFile, OSError) as exc:
        raise ValueError("The uploaded file is not a valid DOCX document.") from exc
    finally:
        upload.seek(0)


def convert_docx_to_pdf(upload):
    _validate_docx(upload)
    executable = _libreoffice_binary()
    if not executable:
        raise ValueError("DOCX conversion requires LibreOffice to be installed on the server.")

    with tempfile.TemporaryDirectory(prefix="necessary-tools-docx-") as directory:
        root = Path(directory)
        source = root / "document.docx"
        profile = root / "libreoffice-profile"
        with source.open("wb") as destination:
            for chunk in upload.chunks():
                destination.write(chunk)
        try:
            process = subprocess.run(
                [
                    executable,
                    "--headless",
                    "--nologo",
                    "--nodefault",
                    "--nofirststartwizard",
                    f"-env:UserInstallation={profile.resolve().as_uri()}",
                    "--convert-to",
                    "pdf:writer_pdf_Export",
                    "--outdir",
                    str(root),
                    str(source),
                ],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ValueError("The DOCX conversion exceeded the two-minute limit.") from exc
        output_path = root / "document.pdf"
        if process.returncode or not output_path.exists():
            raise ValueError("LibreOffice could not convert this DOCX file.")
        result = output_path.read_bytes()
        if not result.startswith(b"%PDF"):
            raise ValueError("The converter did not produce a valid PDF.")
        return BytesIO(result)
