from django.urls import path

from . import views

urlpatterns = [
    path("capabilities", views.capabilities, name="integration_capabilities"),
    path("dishes/suggest", views.dishes_suggest, name="integration_dishes_suggest"),
    path("categories", views.categories, name="integration_categories"),
    path("menu/check", views.menu_check, name="integration_menu_check"),
    path("menu/analyze", views.menu_analyze, name="integration_menu_analyze"),
    path("dishes", views.dishes_create, name="integration_dishes_create"),
    path("dishes/<int:dish_id>", views.dish_detail, name="integration_dish_detail"),
    path("dishes/<int:dish_id>/missing-fields", views.dishes_fill_missing, name="integration_dishes_fill"),
    path("covers", views.covers_list, name="integration_covers"),
    path("covers/<int:cover_id>/image", views.cover_image, name="integration_cover_image"),
    path("menu/pdf", views.menu_pdf, name="integration_menu_pdf"),
    path("operations/<str:request_id>", views.operation_status, name="integration_operation"),
]
