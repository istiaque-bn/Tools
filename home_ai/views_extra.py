import base64
import io
import json
import re
import textwrap
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import fitz
import qrcode
from accounts.decorators import user_required
from django.http import FileResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST
from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageFilter, ImageFont, ImageOps


MAX_UPLOAD = 25 * 1024 * 1024


def _download(data, name, content_type):
    stream = data if hasattr(data, "read") else io.BytesIO(data)
    stream.seek(0)
    return FileResponse(stream, as_attachment=True, filename=name, content_type=content_type)


def _safe_name(name):
    return re.sub(r"[^A-Za-z0-9._-]+", "-", Path(name).name).strip(".-") or "file"


def _image(upload):
    if not upload or upload.size > MAX_UPLOAD:
        raise ValueError("Choose an image no larger than 25 MB.")
    try:
        result = Image.open(upload)
        result.load()
        return ImageOps.exif_transpose(result)
    except OSError as exc:
        raise ValueError("That file is not a supported image.") from exc


@user_required
def qr_toolkit(request):
    context = {}
    if request.method == "POST":
        try:
            action = request.POST.get("action", "generate")
            if action == "generate":
                kind = request.POST.get("kind", "text")
                value = request.POST.get("value", "").strip()
                if not value:
                    raise ValueError("Enter content for the QR code.")
                if kind == "wifi":
                    value = f"WIFI:T:{request.POST.get('security', 'WPA')};S:{value};P:{request.POST.get('password', '')};;"
                elif kind == "email":
                    value = "mailto:" + value
                elif kind == "phone":
                    value = "tel:" + value
                color = ImageColor.getrgb(request.POST.get("color", "#071a3d"))
                qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=12, border=4)
                qr.add_data(value)
                qr.make(fit=True)
                output = io.BytesIO()
                qr.make_image(fill_color=color, back_color="white").save(output, "PNG")
                return _download(output, "qr-code.png", "image/png")
            image = _image(request.FILES.get("image_file")).convert("RGB")
            detector = getattr(fitz, "barcode", None)
            if detector is None:
                raise ValueError("QR scanning is unavailable in this runtime. QR generation is fully available.")
        except ValueError as exc:
            context["error"] = str(exc)
    return render(request, "qr_toolkit.html", context)


def _text_result(action, text, request):
    if action == "uppercase": return text.upper()
    if action == "lowercase": return text.lower()
    if action == "titlecase": return text.title()
    if action == "sentence": return text[:1].upper() + text[1:].lower()
    if action == "trim": return "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if action == "dedupe": return "\n".join(dict.fromkeys(text.splitlines()))
    if action == "sort": return "\n".join(sorted(text.splitlines(), key=str.casefold))
    if action == "slug": return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if action == "reverse": return text[::-1]
    if action == "json": return json.dumps(json.loads(text), indent=2, ensure_ascii=False)
    if action == "base64_encode": return base64.b64encode(text.encode()).decode()
    if action == "base64_decode": return base64.b64decode(text, validate=True).decode()
    if action == "url_encode":
        from urllib.parse import quote
        return quote(text)
    if action == "url_decode":
        from urllib.parse import unquote
        return unquote(text)
    if action == "uuid": return str(uuid.uuid4())
    if action == "timestamp":
        value = text.strip()
        return datetime.fromtimestamp(float(value), timezone.utc).isoformat() if value else str(int(datetime.now(timezone.utc).timestamp()))
    if action == "regex":
        matches = re.findall(request.POST.get("pattern", ""), text, re.MULTILINE)
        return json.dumps(matches, indent=2, ensure_ascii=False)
    raise ValueError("Choose a valid operation.")


@user_required
def text_toolkit(request):
    context = {}
    if request.method == "POST":
        text = request.POST.get("text", "")
        try:
            context.update(text=text, result=_text_result(request.POST.get("action", "trim"), text, request), active=request.POST.get("action"))
        except (ValueError, TypeError, json.JSONDecodeError, UnicodeError, re.error) as exc:
            context.update(text=text, error=str(exc))
    return render(request, "text_toolkit.html", context)


@user_required
def batch_images(request):
    context = {}
    if request.method == "POST":
        try:
            uploads = request.FILES.getlist("image_files")
            if not uploads or len(uploads) > 50:
                raise ValueError("Choose between 1 and 50 images.")
            action, archive = request.POST.get("action", "compress"), io.BytesIO()
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
                for upload in uploads:
                    image = _image(upload)
                    if action == "resize":
                        width = int(request.POST.get("width", 1200))
                        image.thumbnail((width, width * 10), Image.Resampling.LANCZOS)
                    elif action == "watermark":
                        draw = ImageDraw.Draw(image)
                        draw.text((16, 16), request.POST.get("watermark", "Necessary Tools"), fill="white", stroke_width=2, stroke_fill="black")
                    output_format = request.POST.get("format", "JPEG").upper()
                    if output_format not in {"JPEG", "PNG", "WEBP"}: raise ValueError("Choose JPG, PNG, or WebP.")
                    if output_format == "JPEG": image = image.convert("RGB")
                    output = io.BytesIO()
                    image.save(output, output_format, quality=int(request.POST.get("quality", 82)), optimize=True)
                    bundle.writestr(Path(_safe_name(upload.name)).stem + "." + {"JPEG":"jpg","PNG":"png","WEBP":"webp"}[output_format], output.getvalue())
            return _download(archive, "processed-images.zip", "application/zip")
        except (ValueError, OSError) as exc:
            context["error"] = str(exc)
    return render(request, "batch_images.html", context)


@user_required
def archive_toolkit(request):
    context = {}
    if request.method == "POST":
        try:
            action = request.POST.get("action", "create")
            if action == "create":
                uploads = request.FILES.getlist("files")
                if not uploads: raise ValueError("Choose at least one file.")
                output = io.BytesIO()
                with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
                    for item in uploads:
                        if item.size > MAX_UPLOAD: raise ValueError("Each file must be 25 MB or smaller.")
                        archive.writestr(_safe_name(item.name), item.read())
                return _download(output, "necessary-tools.zip", "application/zip")
            upload = request.FILES.get("archive")
            if not upload or not zipfile.is_zipfile(upload): raise ValueError("Choose a valid ZIP archive.")
            upload.seek(0)
            with zipfile.ZipFile(upload) as archive:
                entries = [{"name": i.filename, "size": i.file_size, "compressed": i.compress_size} for i in archive.infolist() if not i.is_dir()]
            context["entries"] = entries
        except (ValueError, zipfile.BadZipFile) as exc:
            context["error"] = str(exc)
    return render(request, "archive_toolkit.html", context)


@user_required
def advanced_toolkit(request):
    context = {}
    if request.method == "POST":
        try:
            action = request.POST.get("action")
            upload = request.FILES.get("file")
            if action == "ocr":
                if not upload: raise ValueError("Choose a PDF or image.")
                if upload.name.lower().endswith(".pdf"):
                    doc = fitz.open(stream=upload.read(), filetype="pdf")
                    text = "\n\n".join(page.get_text("text") for page in doc)
                    if not text.strip(): raise ValueError("No embedded text was found. Install Tesseract to OCR scanned pages.")
                else:
                    raise ValueError("Image OCR requires Tesseract; PDF embedded-text extraction is available now.")
                return _download(text.encode(), "extracted-text.txt", "text/plain")
            if action == "sign":
                if not upload or not upload.name.lower().endswith(".pdf"): raise ValueError("Choose a PDF.")
                signature = _image(request.FILES.get("signature")).convert("RGBA")
                doc = fitz.open(stream=upload.read(), filetype="pdf")
                page_no = max(1, int(request.POST.get("page", 1))) - 1
                if page_no >= len(doc): raise ValueError("Signature page is outside the document.")
                sig = io.BytesIO(); signature.save(sig, "PNG")
                x, y = float(request.POST.get("x", 72)), float(request.POST.get("y", 650))
                width = float(request.POST.get("width", 160)); height = width * signature.height / signature.width
                doc[page_no].insert_image(fitz.Rect(x, y, x + width, y + height), stream=sig.getvalue())
                output = io.BytesIO(doc.tobytes(garbage=4, deflate=True))
                return _download(output, "signed.pdf", "application/pdf")
            if action == "background":
                image = _image(upload).convert("RGBA")
                corner = Image.new("RGBA", image.size, image.getpixel((0, 0)))
                difference = ImageChops.difference(image, corner).convert("L").point(lambda p: 0 if p < int(request.POST.get("tolerance", 28)) else 255)
                difference = difference.filter(ImageFilter.GaussianBlur(1))
                image.putalpha(difference)
                output = io.BytesIO(); image.save(output, "PNG")
                return _download(output, "background-removed.png", "image/png")
            if action == "screenshot":
                title, body = request.POST.get("title", "Screenshot"), request.POST.get("content", "")
                image = Image.new("RGB", (1200, 630), "#07152f"); draw = ImageDraw.Draw(image)
                draw.text((70, 65), title[:80], fill="#79a9ff", font=ImageFont.load_default(size=44))
                draw.multiline_text((70, 145), textwrap.fill(body, 65)[:1200], fill="white", spacing=12, font=ImageFont.load_default(size=25))
                output = io.BytesIO(); image.save(output, "PNG")
                return _download(output, "screenshot-card.png", "image/png")
            raise ValueError("Choose a valid advanced tool.")
        except (ValueError, OSError, fitz.FileDataError) as exc:
            context["error"] = str(exc)
    return render(request, "advanced_toolkit.html", context)


@user_required
def dictionary_tool(request):
    query = " ".join(request.GET.get("q", "").split())[:80]
    context = {"query": query}
    if query:
        from .dictionary_provider import DictionaryLookupError, lookup_word
        try:
            context["entry"] = lookup_word(query)
        except DictionaryLookupError as exc:
            context["error"] = str(exc)
    return render(request, "dictionary_tool.html", context)


@require_POST
@user_required
def tools_api(request):
    try:
        payload = json.loads(request.body or b"{}")
        result = _text_result(payload.get("action", "trim"), str(payload.get("text", "")), request)
        return JsonResponse({"ok": True, "result": result})
    except Exception as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
