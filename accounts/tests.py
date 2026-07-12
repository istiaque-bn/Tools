from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from abbreviation_tool.models import DocumentProcessingSession

from .models import UserProfile


User = get_user_model()


class RoleManagementTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("member", email="member@example.com", password="pass12345")
        self.admin = User.objects.create_user("manager", email="manager@example.com", password="pass12345", is_staff=True)

    def test_unauthenticated_user_is_redirected_from_protected_pages(self):
        for name in ("home", "admin_panel:dashboard", "admin_panel:user_list"):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302)
            self.assertIn(reverse("login"), response.url)

    def test_normal_user_can_access_dashboard_but_not_panel(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin_panel:dashboard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin_panel:user_list")).status_code, 403)

    def test_every_new_user_receives_sd_checker_access(self):
        self.assertTrue(self.user.has_perm("abbreviation_tool.access_abbreviation_tool"))
        self.assertTrue(self.user.has_perm("abbreviation_tool.process_document"))
        self.client.force_login(self.user)
        response = self.client.get(reverse("home"))
        self.assertContains(response, "SD Checker")

    def test_admin_can_access_panel_and_user_management(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("admin_panel:dashboard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin_panel:user_list")).status_code, 200)

    def test_admin_can_create_user_and_is_redirected_to_refreshed_list(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("admin_panel:user_list"), {
            "create_user": "1",
            "username": "newmember",
            "first_name": "New",
            "last_name": "Member",
            "email": "new@example.com",
            "role": "user",
            "is_active": "on",
            "password1": "strong-example-password-247",
            "password2": "strong-example-password-247",
        })
        self.assertRedirects(response, reverse("admin_panel:user_list"))
        created = User.objects.get(username="newmember")
        self.assertTrue(created.check_password("strong-example-password-247"))
        self.assertEqual(created.profile.role, UserProfile.Role.USER)

    def test_invalid_creation_keeps_form_open_and_does_not_create_user(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("admin_panel:user_list"), {"create_user": "1", "username": "bad"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["show_create_form"])
        self.assertFalse(User.objects.filter(username="bad").exists())

    def test_admin_can_change_profile_role(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("admin_panel:user_detail", args=[self.user.pk]), {"role": "admin", "is_active": "on"})
        self.assertRedirects(response, reverse("admin_panel:user_detail", args=[self.user.pk]))
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.role, UserProfile.Role.ADMIN)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("admin_panel:dashboard")).status_code, 200)

    def test_normal_user_cannot_change_roles(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("admin_panel:user_detail", args=[self.admin.pk]), {"role": "user", "is_active": "on"})
        self.assertEqual(response.status_code, 403)
        self.admin.profile.refresh_from_db()
        self.assertEqual(self.admin.profile.role, UserProfile.Role.ADMIN)

    def test_admin_cannot_remove_own_access(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("admin_panel:user_detail", args=[self.admin.pk]), {"role": "user"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "cannot remove your own")
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_role_aware_login_redirects(self):
        response = self.client.post(reverse("login"), {"username": "member", "password": "pass12345"})
        self.assertRedirects(response, reverse("home"))
        self.client.post(reverse("logout"))
        response = self.client.post(reverse("login"), {"username": "manager", "password": "pass12345"})
        self.assertRedirects(response, reverse("admin_panel:dashboard"))

    def test_navbar_is_role_aware_and_logout_is_in_dropdown(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("home"))
        self.assertNotContains(response, "Admin Panel")
        self.assertContains(response, 'class="account-dropdown"')
        self.assertContains(response, "Sign out")
        self.client.force_login(self.admin)
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Admin Panel")

    def test_document_session_object_ownership_remains_protected(self):
        # Detailed session ownership is covered by abbreviation_tool tests; this
        # assertion guards that sessions continue to be user-owned.
        self.assertEqual(DocumentProcessingSession._meta.get_field("user").remote_field.model, User)
