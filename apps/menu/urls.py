from django.urls import path

from . import views


app_name = "menu"

urlpatterns = [
    path("", views.index, name="index"),
    path("editor/", views.editor, name="editor"),
    path("archive/", views.archive_page, name="archive"),
    path("archive/<int:entry_id>/download/", views.archive_download, name="archive_download"),
    path("document/<str:token>/print/", views.document_print_page, name="document_print"),
]
