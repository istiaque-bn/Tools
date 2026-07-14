from django.apps import AppConfig


class AbbreviationToolConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "abbreviation_tool"
    verbose_name = "SD Checker"

    def ready(self):
        from django.contrib.auth.models import Group, Permission
        from django.db.models.signals import post_migrate

        def configure_groups(**kwargs):
            standard, _ = Group.objects.get_or_create(name="DOCX Abbreviation Users")
            administrators, _ = Group.objects.get_or_create(
                name="DOCX Abbreviation Administrators"
            )
            standard_codes = {
                "access_abbreviation_tool",
                "process_document",
                "search_dictionary",
            }
            admin_codes = standard_codes | {
                "manage_dictionary",
                "import_dictionary",
                "export_dictionary",
                "manage_profiles",
                "view_audit_log",
            }
            permissions = Permission.objects.filter(
                content_type__app_label="abbreviation_tool"
            )
            standard.permissions.set(permissions.filter(codename__in=standard_codes))
            administrators.permissions.set(permissions.filter(codename__in=admin_codes))

        post_migrate.connect(
            configure_groups,
            sender=self,
            weak=False,
            dispatch_uid="abbreviation_tool_groups",
        )
