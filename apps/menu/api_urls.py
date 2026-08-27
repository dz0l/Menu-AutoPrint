from django.urls import path

from . import views


app_name = "menu_api"

urlpatterns = [
    path("preview", views.preview_api, name="preview"),
    path("analyze", views.analyze_api, name="analyze"),
    path("render", views.render_document_api, name="render"),
    path("pdf", views.pdf_api, name="pdf"),
    path("covers", views.covers_api, name="covers"),
    path("covers/<int:cover_id>", views.cover_detail_api, name="cover_detail"),
    path("covers/<int:cover_id>/image", views.cover_image_api, name="cover_image"),
]
