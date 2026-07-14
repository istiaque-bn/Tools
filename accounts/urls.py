from django.urls import path

from . import views

app_name = "admin_panel"

urlpatterns = [
    path("", views.panel_dashboard, name="dashboard"),
    path("dashboard/", views.panel_dashboard, name="dashboard_alias"),
    path("users/", views.user_list, name="user_list"),
    path("users/<int:user_id>/", views.user_detail, name="user_detail"),
    path("feedback/", views.feedback_list, name="feedback_list"),
    path(
        "feedback/<int:feedback_id>/toggle/",
        views.toggle_feedback,
        name="toggle_feedback",
    ),
    path("audit-log/", views.audit_log, name="audit_log"),
    path("system/", views.system_status, name="system"),
    path("system/database/backup/", views.database_backup, name="database_backup"),
    path("system/database/restore/", views.database_restore, name="database_restore"),
    path("system/audit.csv", views.audit_export, name="audit_export"),
]
