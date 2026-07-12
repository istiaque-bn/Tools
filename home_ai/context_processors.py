from django.conf import settings


def feature_flags(request):
    from accounts.utils import is_admin_user
    return {"docx_abbreviation_tool_enabled": settings.DOCX_ABBREVIATION_TOOL_ENABLED, "is_admin_user": is_admin_user(request.user)}
