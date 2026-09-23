from __future__ import annotations

from django.test import SimpleTestCase, TestCase

from apps.dishes.models import Dish
from apps.integrations.menu_check import check_menu
from apps.menu import document as document_mod
from apps.menu.document import build_document_payload
from apps.menu.services import dish_maps


class AsBoolTests(SimpleTestCase):
    def test_null_and_empty_mean_off(self):
        self.assertFalse(document_mod._as_bool(None, default=True, strict=False))
        self.assertFalse(document_mod._as_bool("", default=True, strict=False))

    def test_missing_key_uses_default_via_get(self):
        # build_document_payload uses data.get("show_kcal", True) before _as_bool
        payload = build_document_payload({"ru": "Супы:\n"}, require_cover=False, dishes={})
        self.assertTrue(payload["show_kcal"])

    def test_explicit_false(self):
        payload = build_document_payload({"ru": "Супы:\n", "show_kcal": False}, require_cover=False, dishes={})
        self.assertFalse(payload["show_kcal"])

    def test_null_show_kcal_turns_off(self):
        payload = build_document_payload({"ru": "Супы:\n", "show_kcal": None}, require_cover=False, dishes={})
        self.assertFalse(payload["show_kcal"])


class CatalogSnapshotTests(TestCase):
    def test_check_and_payload_share_snapshot(self):
        dish = Dish.objects.create(
            name_ru="Борщ",
            name_en="Borscht",
            grams_default=250,
            kcal_per_100=45,
        )
        catalog = dish_maps()
        dish.name_en = ""
        dish.save(update_fields=["name_en"])
        # Live DB no longer has EN; snapshot still does.
        result = check_menu("Супы:\nБорщ", show_kcal=True, dishes=catalog)
        self.assertTrue(result["ready"])
        payload = build_document_payload(
            {"ru": "Супы:\nБорщ", "show_kcal": True, "auto_format": False},
            dishes=catalog,
        )
        en_texts = [item.get("text") for item in payload["preview"]["en"] if item.get("text")]
        self.assertIn("Borscht", en_texts)
        self.assertNotIn("???", en_texts)
