from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from reportlab.pdfgen import canvas

from .models import Abbreviation
from .parser import abbreviation_candidates


class JssdmCheckerTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            "jssdm-user", password="test-password"
        )
        self.client.force_login(self.user)
        Abbreviation.objects.create(
            abbreviation="SITREP", meaning="Situation Report", source_page=441
        )

    def test_checker_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("jssdm:checker")).status_code, 302)

    def test_reference_search(self):
        response = self.client.get(reverse("jssdm:checker"), {"q": "Situation"})
        self.assertContains(response, "SITREP")

    def test_pdf_checker_matches_reference(self):
        output = BytesIO()
        pdf = canvas.Canvas(output)
        pdf.drawString(72, 720, "Submit SITREP and UNKNOWN before 0900.")
        pdf.save()
        upload = SimpleUploadedFile(
            "orders.pdf", output.getvalue(), content_type="application/pdf"
        )
        response = self.client.post(reverse("jssdm:checker"), {"pdf_file": upload})
        self.assertContains(response, "Situation Report")
        self.assertContains(response, "UNKNOWN")

    def test_candidate_extraction(self):
        self.assertEqual(
            abbreviation_candidates("Send SITREP to HQ."), ["HQ", "SITREP"]
        )
