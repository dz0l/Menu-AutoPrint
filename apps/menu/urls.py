from django.urls import path

from . import views


app_name = "menu"

urlpatterns = [
    path("", views.index, name="index"),
    path("editor/", views.editor, name="editor"),
    path("document/<str:token>/", views.document_preview_page, name="document_preview"),
    path("document/<str:token>/pdf/", views.document_pdf_page, name="document_pdf"),
]
