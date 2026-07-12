from django.urls import path

from . import views

app_name = "abbreviation_tool"

urlpatterns = [
    path("", views.landing, name="landing"),
    path("dictionary/", views.dictionary, name="dictionary"),
    path("dictionary/manage/", views.manage_dictionary, name="manage_dictionary"),
    path("dictionary/manage/<int:entry_id>/", views.manage_dictionary, name="edit_dictionary_entry"),
    path("dictionary/manage/<int:entry_id>/delete/", views.delete_dictionary_entry, name="delete_dictionary_entry"),
    path("feedback/", views.feedback, name="feedback"),
    path("text-convert/", views.text_convert, name="text_convert"),
    path("upload/", views.upload, name="upload"),
    path("sessions/<uuid:session_id>/", views.session_detail, name="session"),
    path("sessions/<uuid:session_id>/cancel/", views.cancel, name="cancel"),
    path("sessions/<uuid:session_id>/analyse/", views.analyse, name="analyse"),
    path("sessions/<uuid:session_id>/review/", views.review, name="review"),
    path("sessions/<uuid:session_id>/suggestions/<uuid:suggestion_id>/", views.suggestion_api, name="suggestion_api"),
    path("sessions/<uuid:session_id>/suggestions/bulk/", views.bulk_review_api, name="bulk_review_api"),
    path("sessions/<uuid:session_id>/history/", views.history_api, name="history_api"),
    path("sessions/<uuid:session_id>/generate/", views.generate, name="generate"),
    path("sessions/<uuid:session_id>/summary/", views.summary, name="summary"),
    path("sessions/<uuid:session_id>/download/", views.download, name="download"),
    path("sessions/<uuid:session_id>/glossary/", views.glossary_download, name="glossary_download"),
]
