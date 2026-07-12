from django.urls import path

from . import views

app_name = "admin_panel"

urlpatterns = [
    path("", views.panel_dashboard, name="dashboard"),
    path("dashboard/", views.panel_dashboard, name="dashboard_alias"),
    path("users/", views.user_list, name="user_list"),
    path("users/<int:user_id>/", views.user_detail, name="user_detail"),
    path("feedback/", views.feedback_list, name="feedback_list"),
    path("feedback/<int:feedback_id>/toggle/", views.toggle_feedback, name="toggle_feedback"),
    path("audit-log/", views.audit_log, name="audit_log"),
]
