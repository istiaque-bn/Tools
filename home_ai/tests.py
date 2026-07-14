from io import BytesIO
import zipfile
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from pypdf import PdfReader, PdfWriter
from PIL import Image


def pdf_upload(name, pages=1):
    output = BytesIO()
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    writer.write(output)
    return SimpleUploadedFile(name, output.getvalue(), content_type="application/pdf")


def image_upload(name="sample.png", size=(120, 80), image_format="PNG"):
    output = BytesIO()
    Image.new("RGB", size, (30, 110, 210)).save(output, format=image_format)
    return SimpleUploadedFile(name, output.getvalue(), content_type=f"image/{image_format.lower()}")


class PdfToolkitTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("tester", password="test-password")

    def test_tool_requires_login(self):
        response = self.client.get(reverse("pdf_toolkit"))
        self.assertRedirects(response, reverse("login") + "?next=" + reverse("pdf_toolkit"), fetch_redirect_response=False)

    def test_merge_returns_combined_pdf(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("pdf_toolkit"), {
            "action": "merge",
            "pdf_files": [pdf_upload("one.pdf"), pdf_upload("two.pdf", 2)],
        })
        self.assertEqual(response.status_code, 200)
        merged = b"".join(response.streaming_content)
        self.assertEqual(len(PdfReader(BytesIO(merged)).pages), 3)

    def test_split_returns_requested_range(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("pdf_toolkit"), {
            "action": "split", "pdf_file": pdf_upload("source.pdf", 4),
            "start_page": "2", "end_page": "3",
        })
        self.assertEqual(response.status_code, 200)
        result = b"".join(response.streaming_content)
        self.assertEqual(len(PdfReader(BytesIO(result)).pages), 2)

    def test_split_multiple_ranges_returns_zip_of_pdfs(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("pdf_toolkit"), {
            "action": "split", "pdf_file": pdf_upload("source.pdf", 8),
            "split_ranges": "1-3, 4-6, 8",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/zip")
        archive = zipfile.ZipFile(BytesIO(b"".join(response.streaming_content)))
        self.assertEqual(len(archive.namelist()), 3)
        page_counts = [len(PdfReader(BytesIO(archive.read(name))).pages) for name in archive.namelist()]
        self.assertEqual(page_counts, [3, 3, 1])

    def test_split_multiple_ranges_rejects_out_of_bounds_pages(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("pdf_toolkit"), {
            "action": "split", "pdf_file": pdf_upload("source.pdf", 4),
            "split_ranges": "1-2, 5-6",
        })
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Every range must be between 1 and 4.", status_code=400)

    def test_inspect_displays_details(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("pdf_toolkit"), {
            "action": "inspect", "pdf_file": pdf_upload("details.pdf", 2),
        })
        self.assertContains(response, "details.pdf")
        self.assertContains(response, "<strong>2</strong>", html=True)

    def test_remove_and_reorder_pages(self):
        self.client.force_login(self.user)
        removed = self.client.post(reverse("pdf_toolkit"), {
            "action": "remove", "pdf_file": pdf_upload("source.pdf", 4), "pages": "2,4",
        })
        self.assertEqual(len(PdfReader(BytesIO(b"".join(removed.streaming_content))).pages), 2)
        organized = self.client.post(reverse("pdf_toolkit"), {
            "action": "organize", "pdf_file": pdf_upload("source.pdf", 3), "pages": "3,1,2,1",
        })
        self.assertEqual(len(PdfReader(BytesIO(b"".join(organized.streaming_content))).pages), 4)

    def test_watermark_and_page_numbers(self):
        self.client.force_login(self.user)
        for action in ("watermark", "number"):
            data = {"action": action, "pdf_file": pdf_upload("source.pdf", 2)}
            if action == "watermark":
                data["watermark_text"] = "CONFIDENTIAL"
            response = self.client.post(reverse("pdf_toolkit"), data)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(PdfReader(BytesIO(b"".join(response.streaming_content))).pages), 2)

    def test_protect_and_unlock(self):
        self.client.force_login(self.user)
        protected = self.client.post(reverse("pdf_toolkit"), {
            "action": "protect", "pdf_file": pdf_upload("source.pdf"), "new_password": "secret12",
        })
        encrypted_bytes = b"".join(protected.streaming_content)
        self.assertTrue(PdfReader(BytesIO(encrypted_bytes)).is_encrypted)
        unlocked = self.client.post(reverse("pdf_toolkit"), {
            "action": "unlock",
            "pdf_file": SimpleUploadedFile("locked.pdf", encrypted_bytes, content_type="application/pdf"),
            "current_password": "secret12",
        })
        unlocked_reader = PdfReader(BytesIO(b"".join(unlocked.streaming_content)))
        self.assertFalse(unlocked_reader.is_encrypted)

    def test_preview_returns_page_thumbnails(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("pdf_preview"), {"pdf_file": pdf_upload("preview.pdf", 2)})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["pages"]), 2)
        self.assertTrue(payload["pages"][0]["thumbnail"].startswith("data:image/jpeg;base64,"))

    def test_rotate_only_selected_page(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("pdf_toolkit"), {
            "action": "rotate", "pdf_file": pdf_upload("source.pdf", 3),
            "rotations": '{"2": 90}',
        })
        reader = PdfReader(BytesIO(b"".join(response.streaming_content)))
        self.assertEqual(reader.pages[0].rotation, 0)
        self.assertEqual(reader.pages[1].rotation, 90)
        self.assertEqual(reader.pages[2].rotation, 0)

    @patch("home_ai.document_conversion.convert_docx_to_pdf")
    def test_docx_to_pdf_returns_download(self, converter):
        self.client.force_login(self.user)
        pdf = BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        writer.write(pdf)
        pdf.seek(0)
        converter.return_value = pdf
        upload = SimpleUploadedFile(
            "report.docx",
            b"test document",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

        response = self.client.post(reverse("pdf_toolkit"), {"action": "docx_to_pdf", "docx_files": [upload]})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("report.pdf", response["Content-Disposition"])
        self.assertEqual(len(PdfReader(BytesIO(b"".join(response.streaming_content))).pages), 1)

    @patch("home_ai.document_conversion.convert_docx_to_pdf")
    def test_multiple_docx_files_return_zip_of_pdfs(self, converter):
        self.client.force_login(self.user)

        def converted(_upload):
            output = BytesIO()
            writer = PdfWriter()
            writer.add_blank_page(width=612, height=792)
            writer.write(output)
            output.seek(0)
            return output

        converter.side_effect = converted
        uploads = [
            SimpleUploadedFile("one.docx", b"one"),
            SimpleUploadedFile("two.docx", b"two"),
        ]

        response = self.client.post(reverse("pdf_toolkit"), {"action": "docx_to_pdf", "docx_files": uploads})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/zip")
        archive = zipfile.ZipFile(BytesIO(b"".join(response.streaming_content)))
        self.assertEqual(archive.namelist(), ["one.pdf", "two.pdf"])
        for name in archive.namelist():
            self.assertEqual(len(PdfReader(BytesIO(archive.read(name))).pages), 1)


class ImageToolkitTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("image-tester", password="test-password")
        self.client.force_login(self.user)

    def image_response(self, data):
        response = self.client.post(reverse("image_toolkit"), data)
        self.assertEqual(response.status_code, 200)
        return Image.open(BytesIO(b"".join(response.streaming_content)))

    def test_tool_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("image_toolkit"))
        self.assertEqual(response.status_code, 302)

    def test_compress_and_convert(self):
        compressed = self.image_response({"action": "compress_image", "image_file": image_upload(), "quality": "65"})
        self.assertEqual(compressed.size, (120, 80))
        converted = self.image_response({"action": "convert_image", "image_file": image_upload(), "output_format": "WEBP"})
        self.assertEqual(converted.format, "WEBP")

    def test_resize_and_transform(self):
        resized = self.image_response({"action": "resize_image", "image_file": image_upload(), "width": "60", "height": "40"})
        self.assertEqual(resized.size, (60, 40))
        rotated = self.image_response({"action": "transform_image", "image_file": image_upload(), "transform": "rotate_90"})
        self.assertEqual(rotated.size, (80, 120))

    def test_crop_returns_only_selected_region(self):
        cropped = self.image_response({
            "action": "crop_image", "image_file": image_upload(size=(120, 80)),
            "crop_x": "20", "crop_y": "10", "crop_width": "50", "crop_height": "30",
        })
        self.assertEqual(cropped.size, (50, 30))

    def test_inspect_displays_image_details(self):
        response = self.client.post(reverse("image_toolkit"), {"action": "inspect_image", "image_file": image_upload()})
        self.assertContains(response, "120")
        self.assertContains(response, "PNG")

    def test_mouse_positioned_watermark_output(self):
        watermarked = self.image_response({
            "action": "watermark_image", "image_file": image_upload(size=(300, 200)),
            "watermark_text": "TEST", "watermark_size": "8", "watermark_opacity": "70",
            "watermark_x": "20", "watermark_y": "25",
        })
        self.assertEqual(watermarked.size, (300, 200))


class ExpandedToolkitTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("tools-user", password="test-password")
        self.client.force_login(self.user)

    def test_new_tool_pages_open(self):
        for name in ("qr_toolkit", "text_toolkit", "batch_images", "archive_toolkit", "advanced_toolkit"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_qr_generation_returns_png(self):
        response = self.client.post(reverse("qr_toolkit"), {"action": "generate", "kind": "text", "value": "https://example.com"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")

    def test_text_tools_and_api(self):
        response = self.client.post(reverse("text_toolkit"), {"action": "json", "text": '{"ready":true}'})
        self.assertContains(response, '&quot;ready&quot;: true')
        api = self.client.post(reverse("tools_api"), json.dumps({"action": "slug", "text": "Hello New World"}), content_type="application/json")
        self.assertEqual(api.json()["result"], "hello-new-world")

    def test_batch_images_returns_zip(self):
        response = self.client.post(reverse("batch_images"), {"action": "compress", "format": "PNG", "image_files": [image_upload("one.png"), image_upload("two.png")]})
        self.assertEqual(response["Content-Type"], "application/zip")
        archive = zipfile.ZipFile(BytesIO(b"".join(response.streaming_content)))
        self.assertEqual(len(archive.namelist()), 2)

    def test_archive_create_and_inspect(self):
        file = SimpleUploadedFile("note.txt", b"hello", content_type="text/plain")
        created = self.client.post(reverse("archive_toolkit"), {"action": "create", "files": [file]})
        data = b"".join(created.streaming_content)
        inspected = self.client.post(reverse("archive_toolkit"), {"action": "inspect", "archive": SimpleUploadedFile("test.zip", data)})
        self.assertContains(inspected, "note.txt")
