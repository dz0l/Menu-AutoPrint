from django.urls import path

from . import views


app_name = "menu_api"

urlpatterns = [
    path("preview", views.preview_api, name="preview"),
    path("analyze", views.analyze_api, name="analyze"),
    path("render", views.render_document_api, name="render"),
    path("pdf", views.pdf_api, name="pdf"),
]
