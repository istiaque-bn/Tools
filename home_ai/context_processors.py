from django.conf import settings


def feature_flags(request):
    return {"docx_abbreviation_tool_enabled": settings.DOCX_ABBREVIATION_TOOL_ENABLED}
