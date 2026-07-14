from django.contrib import admin
from django.urls import include, path

from . import views
from . import views_extra

handler403 = views.permission_denied_view

urlpatterns = [
    path("", views.home_view, name="home"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("tools/pdf/", views.pdf_toolkit_view, name="pdf_toolkit"),
    path("tools/pdf/preview/", views.pdf_preview_view, name="pdf_preview"),
    path("tools/images/", views.image_toolkit_view, name="image_toolkit"),
    path("tools/qr/", views_extra.qr_toolkit, name="qr_toolkit"),
    path("tools/text/", views_extra.text_toolkit, name="text_toolkit"),
    path("tools/images/batch/", views_extra.batch_images, name="batch_images"),
    path("tools/archive/", views_extra.archive_toolkit, name="archive_toolkit"),
    path("tools/advanced/", views_extra.advanced_toolkit, name="advanced_toolkit"),
    path("tools/dictionary/", views_extra.dictionary_tool, name="dictionary_tool"),
    path("tools/jssdm/", include("jssdm.urls")),
    path("tools/docx-abbreviations/", include("abbreviation_tool.urls")),
    path("api/v1/tools/text/", views_extra.tools_api, name="tools_api"),
    path("panel/", include("accounts.urls")),
    path("admin/", admin.site.urls),
]
