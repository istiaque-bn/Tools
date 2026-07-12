import base64
import json
import zipfile
from io import BytesIO

import fitz
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps, UnidentifiedImageError
from reportlab.pdfgen import canvas
from django.utils.http import url_has_allowed_host_and_scheme

from accounts.decorators import user_required
from accounts.utils import is_admin_user


MAX_IMAGE_SIZE = 25 * 1024 * 1024
IMAGE_FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp", "GIF": "gif"}


def _valid_pdf(upload):
    return upload and upload.name.lower().endswith(".pdf")


def _download(writer, filename):
    output = BytesIO()
    writer.write(output)
    output.seek(0)
    return FileResponse(output, as_attachment=True, filename=filename, content_type="application/pdf")


def _reader(upload, password=""):
    if not _valid_pdf(upload):
        raise ValueError("Choose a valid PDF file.")
    reader = PdfReader(upload)
    if reader.is_encrypted and not reader.decrypt(password):
        raise ValueError("This PDF needs the correct password.")
    return reader


def _page_numbers(spec, total):
    if not spec.strip():
        raise ValueError("Enter at least one page number.")
    result = []
    for part in spec.replace(" ", "").split(","):
        if "-" in part:
            start, end = (int(value) for value in part.split("-", 1))
            result.extend(range(start, end + 1))
        else:
            result.append(int(part))
    if not result or any(page < 1 or page > total for page in result):
        raise ValueError(f"Page numbers must be between 1 and {total}.")
    return result


def _split_ranges(spec, total):
    """Parse comma-separated single pages/ranges into separate PDF groups."""
    groups = []
    for item in spec.replace(" ", "").split(","):
        if not item:
            raise ValueError("Enter ranges like 1-3, 4-6, 8.")
        try:
            if "-" in item:
                start_text, end_text = item.split("-", 1)
                start, end = int(start_text), int(end_text)
            else:
                start = end = int(item)
        except ValueError as exc:
            raise ValueError("Enter ranges like 1-3, 4-6, 8.") from exc
        if start < 1 or end < start or end > total:
            raise ValueError(f"Every range must be between 1 and {total}.")
        groups.append((start, end))
    if not groups:
        raise ValueError("Enter at least one page range.")
    return groups


def _overlay_page(width, height, text, position="center", page_number=None):
    stream = BytesIO()
    layer = canvas.Canvas(stream, pagesize=(width, height))
    layer.setFillAlpha(0.28 if page_number is None else 0.75)
    layer.setFillColorRGB(0.18, 0.34, 0.65)
    if page_number is not None:
        layer.setFont("Helvetica", 10)
        layer.drawCentredString(width / 2, 22, str(page_number))
    else:
        layer.saveState()
        layer.translate(width / 2, height / 2)
        layer.rotate(35)
        layer.setFont("Helvetica-Bold", min(42, max(18, width / max(len(text), 10))))
        layer.drawCentredString(0, 0, text)
        layer.restoreState()
    layer.save()
    stream.seek(0)
    return PdfReader(stream).pages[0]


def _open_image(upload):
    if not upload:
        raise ValueError("Choose an image first.")
    try:
        image = Image.open(upload)
        image.load()
        return ImageOps.exif_transpose(image)
    except (UnidentifiedImageError, OSError):
        raise ValueError("The selected file is not a supported image.")


def _image_download(image, output_format, filename, quality=88):
    output_format = output_format.upper()
    if output_format not in IMAGE_FORMATS:
        raise ValueError("Choose JPG, PNG, WebP, or GIF output.")
    if output_format == "JPEG" and image.mode not in {"RGB", "L"}:
        background = Image.new("RGB", image.size, "white")
        background.paste(image, mask=image.getchannel("A") if "A" in image.getbands() else None)
        image = background
    output = BytesIO()
    options = {"optimize": True}
    if output_format in {"JPEG", "WEBP"}:
        options["quality"] = max(1, min(100, int(quality)))
    image.save(output, format=output_format, **options)
    output.seek(0)
    extension = IMAGE_FORMATS[output_format]
    return FileResponse(output, as_attachment=True, filename=f"{filename}.{extension}", content_type=f"image/{'jpeg' if output_format == 'JPEG' else extension}")


def login_view(request):
    if request.user.is_authenticated:
        return redirect("admin_panel:dashboard" if is_admin_user(request.user) else "home")

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            next_url = request.POST.get("next") or request.GET.get("next")
            if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
                return redirect(next_url)
            return redirect("admin_panel:dashboard" if is_admin_user(user) else "home")

        messages.error(request, "The username or password you entered is incorrect.")

    return render(request, "login.html")


@user_required
def home_view(request):
    from django.conf import settings
    return render(request, "home.html", {"docx_abbreviation_tool_enabled": settings.DOCX_ABBREVIATION_TOOL_ENABLED})


def logout_view(request):
    if request.method == "POST":
        from abbreviation_tool.storage import cleanup_user_sessions
        cleanup_user_sessions(request.user)
        logout(request)
    return redirect("login")


def permission_denied_view(request, exception=None):
    return render(request, "403.html", status=403)


@user_required
def pdf_toolkit_view(request):
    context = {}
    if request.method != "POST":
        return render(request, "pdf_toolkit.html", context)

    action = request.POST.get("action")
    try:
        if action == "merge":
            uploads = request.FILES.getlist("pdf_files")
            if len(uploads) < 2:
                raise ValueError("Choose at least two PDF files to merge.")
            if any(not _valid_pdf(upload) for upload in uploads):
                raise ValueError("Every selected file must be a valid PDF.")

            writer = PdfWriter()
            total_pages = 0
            for upload in uploads:
                reader = PdfReader(upload)
                if reader.is_encrypted:
                    raise ValueError(f"{upload.name} is password protected.")
                for page in reader.pages:
                    writer.add_page(page)
                    total_pages += 1
            if not total_pages:
                raise ValueError("The selected PDFs do not contain any pages.")
            return _download(writer, "necessary-tools-merged.pdf")

        if action == "split":
            upload = request.FILES.get("pdf_file")
            if not _valid_pdf(upload):
                raise ValueError("Choose a valid PDF file.")
            reader = PdfReader(upload)
            if reader.is_encrypted:
                raise ValueError("Password-protected PDFs are not supported yet.")
            ranges_spec = request.POST.get("split_ranges", "").strip()
            if ranges_spec:
                ranges = _split_ranges(ranges_spec, len(reader.pages))
                archive = BytesIO()
                with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
                    for part, (start, end) in enumerate(ranges, start=1):
                        writer = PdfWriter()
                        for index in range(start - 1, end):
                            writer.add_page(reader.pages[index])
                        pdf = BytesIO()
                        writer.write(pdf)
                        label = f"page-{start}" if start == end else f"pages-{start}-to-{end}"
                        bundle.writestr(f"part-{part:02d}-{label}.pdf", pdf.getvalue())
                archive.seek(0)
                return FileResponse(
                    archive,
                    as_attachment=True,
                    filename="split-pdfs.zip",
                    content_type="application/zip",
                )
            start = int(request.POST.get("start_page", "1"))
            end = int(request.POST.get("end_page", str(len(reader.pages))))
            if start < 1 or end < start or end > len(reader.pages):
                raise ValueError(f"Enter a page range between 1 and {len(reader.pages)}.")
            writer = PdfWriter()
            for index in range(start - 1, end):
                writer.add_page(reader.pages[index])
            return _download(writer, f"pages-{start}-to-{end}.pdf")

        if action == "inspect":
            upload = request.FILES.get("pdf_file")
            if not _valid_pdf(upload):
                raise ValueError("Choose a valid PDF file.")
            reader = PdfReader(upload)
            metadata = reader.metadata or {}
            first_page = reader.pages[0] if reader.pages else None
            context["details"] = {
                "name": upload.name,
                "size": f"{upload.size / (1024 * 1024):.2f} MB",
                "pages": len(reader.pages),
                "encrypted": "Yes" if reader.is_encrypted else "No",
                "title": metadata.get("/Title") or "Not specified",
                "author": metadata.get("/Author") or "Not specified",
                "page_size": (
                    f"{float(first_page.mediabox.width):.0f} × {float(first_page.mediabox.height):.0f} pt"
                    if first_page else "Not available"
                ),
            }
            context["active_tool"] = "inspect"
            return render(request, "pdf_toolkit.html", context)

        if action in {"remove", "extract", "organize"}:
            upload = request.FILES.get("pdf_file")
            reader = _reader(upload)
            selected = _page_numbers(request.POST.get("pages", ""), len(reader.pages))
            if action == "remove":
                selected_set = set(selected)
                chosen = [page for page in range(1, len(reader.pages) + 1) if page not in selected_set]
                filename = "pages-removed.pdf"
                if not chosen:
                    raise ValueError("You cannot remove every page from the document.")
            else:
                chosen = selected
                filename = "extracted-pages.pdf" if action == "extract" else "organized-pages.pdf"
            writer = PdfWriter()
            for page in chosen:
                writer.add_page(reader.pages[page - 1])
            return _download(writer, filename)

        if action == "rotate":
            reader = _reader(request.FILES.get("pdf_file"))
            rotations = json.loads(request.POST.get("rotations", "{}"))
            if not rotations:
                raise ValueError("Rotate at least one page using its preview button.")
            writer = PdfWriter()
            for index, page in enumerate(reader.pages, start=1):
                degrees = int(rotations.get(str(index), 0)) % 360
                if degrees not in {0, 90, 180, 270}:
                    raise ValueError("A page has an invalid rotation value.")
                writer.add_page(page.rotate(degrees) if degrees else page)
            return _download(writer, "rotated.pdf")

        if action == "compress":
            reader = _reader(request.FILES.get("pdf_file"))
            writer = PdfWriter()
            for page in reader.pages:
                page.compress_content_streams()
                writer.add_page(page)
            writer.add_metadata(reader.metadata or {})
            return _download(writer, "compressed.pdf")

        if action in {"watermark", "number"}:
            reader = _reader(request.FILES.get("pdf_file"))
            text = request.POST.get("watermark_text", "").strip()
            if action == "watermark" and not text:
                raise ValueError("Enter watermark text.")
            writer = PdfWriter()
            for index, page in enumerate(reader.pages, start=1):
                width, height = float(page.mediabox.width), float(page.mediabox.height)
                page.merge_page(_overlay_page(width, height, text, page_number=index if action == "number" else None))
                writer.add_page(page)
            return _download(writer, "numbered.pdf" if action == "number" else "watermarked.pdf")

        if action == "protect":
            reader = _reader(request.FILES.get("pdf_file"))
            password = request.POST.get("new_password", "")
            if len(password) < 6:
                raise ValueError("Use a password of at least 6 characters.")
            writer = PdfWriter()
            writer.append_pages_from_reader(reader)
            writer.encrypt(password)
            return _download(writer, "protected.pdf")

        if action == "unlock":
            password = request.POST.get("current_password", "")
            reader = _reader(request.FILES.get("pdf_file"), password)
            writer = PdfWriter()
            writer.append_pages_from_reader(reader)
            return _download(writer, "unlocked.pdf")

        if action == "image_to_pdf":
            uploads = request.FILES.getlist("image_files")
            if not uploads:
                raise ValueError("Choose at least one JPG or PNG image.")
            images = []
            for upload in uploads:
                if upload.size > MAX_IMAGE_SIZE or not upload.name.lower().endswith((".jpg", ".jpeg", ".png")):
                    raise ValueError("Use JPG or PNG images no larger than 25 MB each.")
                image = Image.open(upload).convert("RGB")
                images.append(image.copy())
            output = BytesIO()
            images[0].save(output, "PDF", save_all=True, append_images=images[1:])
            output.seek(0)
            return FileResponse(output, as_attachment=True, filename="images.pdf", content_type="application/pdf")

        raise ValueError("Select a valid PDF action.")
    except (PdfReadError, ValueError, TypeError, OSError) as exc:
        context["error"] = str(exc) or "This PDF could not be processed."
        context["active_tool"] = action if action in {"merge", "split", "inspect"} else "merge"
        return render(request, "pdf_toolkit.html", context, status=400)


@user_required
def pdf_preview_view(request):
    if request.method != "POST":
        return JsonResponse({"error": "Upload a PDF to create previews."}, status=405)
    upload = request.FILES.get("pdf_file")
    if not _valid_pdf(upload):
        return JsonResponse({"error": "Choose a valid PDF file."}, status=400)
    try:
        document = fitz.open(stream=upload.read(), filetype="pdf")
        if document.needs_pass:
            return JsonResponse({"error": "Password-protected PDFs cannot be previewed yet."}, status=400)
        pages = []
        matrix = fitz.Matrix(0.32, 0.32)
        for index, page in enumerate(document):
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            pages.append({
                "number": index + 1,
                "thumbnail": "data:image/jpeg;base64," + base64.b64encode(pixmap.tobytes("jpeg", jpg_quality=70)).decode("ascii"),
                "width": round(page.rect.width),
                "height": round(page.rect.height),
            })
        document.close()
        return JsonResponse({"pages": pages, "filename": upload.name})
    except (fitz.FileDataError, RuntimeError, ValueError) as exc:
        return JsonResponse({"error": str(exc) or "This PDF could not be previewed."}, status=400)


@user_required
def image_toolkit_view(request):
    if request.method != "POST":
        return render(request, "image_toolkit.html")
    action = request.POST.get("action", "compress_image")
    try:
        upload = request.FILES.get("image_file")
        image = _open_image(upload)
        source_format = (image.format or "PNG").upper()
        safe_format = source_format if source_format in IMAGE_FORMATS else "PNG"

        if action == "inspect_image":
            return render(request, "image_toolkit.html", {"active_image_tool": action, "image_details": {
                "name": upload.name, "format": source_format, "mode": image.mode,
                "width": image.width, "height": image.height,
                "megapixels": f"{image.width * image.height / 1_000_000:.2f} MP",
                "file_size": f"{upload.size / (1024 * 1024):.2f} MB",
                "animated": "Yes" if getattr(image, "is_animated", False) else "No",
                "metadata_fields": len(image.getexif()),
            }})

        if action == "compress_image":
            return _image_download(image, safe_format, "compressed", request.POST.get("quality", 75))

        if action == "resize_image":
            width, height = int(request.POST.get("width", 0) or 0), int(request.POST.get("height", 0) or 0)
            if width < 1 and height < 1:
                raise ValueError("Enter a width or height.")
            if request.POST.get("keep_aspect") == "on":
                if width < 1:
                    width = round(image.width * height / image.height)
                elif height < 1:
                    height = round(image.height * width / image.width)
                else:
                    ratio = min(width / image.width, height / image.height)
                    width, height = round(image.width * ratio), round(image.height * ratio)
            if width < 1 or height < 1 or width * height > 200_000_000:
                raise ValueError("Resulting dimensions must be valid and below 200 megapixels.")
            return _image_download(image.resize((width, height), Image.Resampling.LANCZOS), safe_format, "resized")

        if action == "crop_image":
            left, top = int(request.POST.get("crop_x", 0)), int(request.POST.get("crop_y", 0))
            width, height = int(request.POST.get("crop_width", 0)), int(request.POST.get("crop_height", 0))
            if width < 1 or height < 1 or left < 0 or top < 0 or left + width > image.width or top + height > image.height:
                raise ValueError("Crop selection must stay inside the image.")
            return _image_download(image.crop((left, top, left + width, top + height)), safe_format, "cropped")

        if action == "transform_image":
            transform = request.POST.get("transform", "rotate_90")
            operations = {"normal": lambda img: img.copy(), "rotate_90": lambda img: img.rotate(-90, expand=True), "rotate_180": lambda img: img.rotate(180, expand=True), "rotate_270": lambda img: img.rotate(-270, expand=True)}
            if transform not in operations:
                raise ValueError("Choose a valid rotation or flip.")
            return _image_download(operations[transform](image), safe_format, "transformed")

        if action == "convert_image":
            return _image_download(image, request.POST.get("output_format", "PNG"), "converted", request.POST.get("quality", 88))

        if action == "watermark_image":
            text = request.POST.get("watermark_text", "").strip()
            if not text:
                raise ValueError("Enter watermark text.")
            working = image.convert("RGBA")
            layer = Image.new("RGBA", working.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(layer)
            font_size = max(14, round(min(image.size) * int(request.POST.get("watermark_size", 5)) / 100))
            try:
                font = ImageFont.truetype("Arial.ttf", font_size)
            except OSError:
                font = ImageFont.load_default(size=font_size)
            box = draw.textbbox((0, 0), text, font=font)
            padding = max(12, font_size // 2)
            default_x = working.width - (box[2] - box[0]) - padding
            default_y = working.height - (box[3] - box[1]) - padding
            position = (
                max(0, min(working.width - (box[2] - box[0]), int(request.POST.get("watermark_x", default_x)))),
                max(0, min(working.height - (box[3] - box[1]), int(request.POST.get("watermark_y", default_y)))),
            )
            opacity = max(20, min(100, int(request.POST.get("watermark_opacity", 55))))
            draw.text(position, text, font=font, fill=(255, 255, 255, round(255 * opacity / 100)), stroke_width=max(1, font_size // 25), stroke_fill=(0, 0, 0, round(150 * opacity / 100)))
            return _image_download(Image.alpha_composite(working, layer), safe_format, "watermarked")

        if action == "adjust_image":
            result = image.convert("RGB")
            result = ImageEnhance.Brightness(result).enhance(float(request.POST.get("brightness", 100)) / 100)
            result = ImageEnhance.Contrast(result).enhance(float(request.POST.get("contrast", 100)) / 100)
            result = ImageEnhance.Color(result).enhance(float(request.POST.get("saturation", 100)) / 100)
            result = ImageEnhance.Sharpness(result).enhance(float(request.POST.get("sharpness", 100)) / 100)
            if request.POST.get("grayscale") == "on":
                result = ImageOps.grayscale(result)
            blur = float(request.POST.get("blur", 0))
            if blur:
                result = result.filter(ImageFilter.GaussianBlur(min(20, blur)))
            return _image_download(result, safe_format, "adjusted")

        if action == "strip_metadata":
            clean = Image.new(image.mode, image.size)
            clean.putdata(list(image.getdata()))
            return _image_download(clean, safe_format, "metadata-removed")

        if action == "image_base64":
            upload.seek(0)
            encoded = base64.b64encode(upload.read()).decode("ascii")
            response = HttpResponse(f"data:{Image.MIME.get(source_format, 'application/octet-stream')};base64,{encoded}", content_type="text/plain; charset=utf-8")
            response["Content-Disposition"] = 'attachment; filename="image-base64.txt"'
            return response
        raise ValueError("Choose a valid image operation.")
    except (ValueError, TypeError, OSError, Image.DecompressionBombError) as exc:
        return render(request, "image_toolkit.html", {"image_error": str(exc), "active_image_tool": action}, status=400)
