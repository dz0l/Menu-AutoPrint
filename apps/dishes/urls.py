from django.urls import path

from . import views


app_name = "dishes"

urlpatterns = [
    path("", views.dishes, name="dishes"),
    path("<int:dish_id>", views.dish_detail, name="dish_detail"),
    path("names", views.names_view, name="names"),
    path("suggest", views.suggest_view, name="suggest"),
    path("export.csv", views.export_csv, name="export_csv"),
    path("import.csv", views.import_csv, name="import_csv"),
    path("bulk-upsert", views.bulk_upsert, name="bulk_upsert"),
    path("check-missing-fixables", views.check_missing_fixables_view, name="check_missing_fixables"),
]
