from __future__ import annotations

import json

from django.template.loader import render_to_string
from django.test import SimpleTestCase, TestCase

from apps.dishes.models import Dish
from apps.integrations.menu_check import check_menu
from apps.menu import document as document_mod
from apps.menu.document import build_document_payload
from apps.menu.services import dish_maps
from datetime import date

from apps.menu.document import archive_conflict_status, validate_editor_menu_input
from apps.menu.models import MenuArchiveEntry
from apps.pdf.layout import TextBlock, _block_height, html_block_height, page_frame
from apps.pdf.render import font_baseline_ratio, resolve_menu_font_files


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


class PrintFrameTests(SimpleTestCase):
    def test_print_page_uses_pdf_frame(self):
        frame = page_frame()
        html = render_to_string(
            "menu/print.html",
            {
                "filename": "menu.pdf",
                "display_date": "25.09.2026",
                "show_kcal": True,
                "background_data": "",
                "page_frame": frame,
                "pages": [
                    {
                        "label": "RU",
                        "layout": {
                            "menu_font_size": 18,
                            "menu_leading": 24,
                            "group_font_size": 18,
                            "group_leading": 24,
                            "continuation_leading": 20,
                            "group_space_before": 16,
                            "after_group_space_before": 5,
                            "dish_space_before": 2,
                        },
                        "items": [{"type": "dish", "lines": ["• Борщ", "250 г"]}],
                        "footer_note": "Калорийность и вес указаны на порцию",
                    }
                ],
            },
        )
        self.assertIn(
            f"padding: {frame['content_top']}pt {frame['margin_x']}pt {frame['content_bottom']}pt",
            html,
        )
        self.assertIn(f"bottom: {frame['footer_y']}pt", html)
        self.assertIn(f"font-size: {frame['footer_font']}pt", html)
        self.assertIn("--group-leading: 24pt", html)
        self.assertIn("overflow-wrap: normal", html)
        self.assertNotIn("overflow-wrap: anywhere", html)
        self.assertIn("padding-bottom: calc(var(--menu-leading, 28pt) - var(--menu-font-size, 20pt))", html)
        self.assertIn("height: var(--menu-font-size, 20pt)", html)


class BlockSpacingTests(SimpleTestCase):
    def test_html_block_height_matches_pdf(self):
        cases = [
            TextBlock(["• Борщ"], "Times", 20, 28, 24, 0, is_dish=True),
            TextBlock(["• Борщ"], "Times", 20, 28, 24, 2, is_dish=True),
            TextBlock(["• Борщ", "250 г"], "Times", 20, 28, 24, 0, is_dish=True),
            TextBlock(["• Борщ", "250 г", "ещё"], "Times", 18, 24, 20, 2, is_dish=True),
            TextBlock(["Супы:"], "Times", 20, 28, 28, 20, is_dish=False),
            TextBlock(["Супы:", "продолжение"], "Times", 16, 22, 22, 6, is_dish=False),
        ]
        for block in cases:
            self.assertEqual(html_block_height(block), _block_height(block))

    def test_bundled_font_baseline_matches_hhea(self):
        files = resolve_menu_font_files()
        self.assertIsNotNone(files)
        self.assertAlmostEqual(font_baseline_ratio(files[0]), 0.825, places=3)


class EditorContractTests(SimpleTestCase):
    def test_non_string_ru_and_date_rejected(self):
        with self.assertRaisesMessage(ValueError, "ru must be a string"):
            validate_editor_menu_input({"ru": 12})
        with self.assertRaisesMessage(ValueError, "print_date must be a string"):
            validate_editor_menu_input({"ru": "Супы:", "print_date": 20260926})
        validate_editor_menu_input({"ru": "Супы:", "print_date": "", "show_kcal": None})


class ArchiveConflictTests(TestCase):
    def test_existing_row_is_reported_without_a_second_write(self):
        MenuArchiveEntry.objects.create(
            menu_date=date(2026, 9, 26),
            menu_type="main",
            location_key="unknown_location",
            display_name="26092026",
            relative_path="menu_archive/2026-09-26_main_unknown_location.pdf",
            file_size=4,
        )
        status = archive_conflict_status({"ru": "Супы:\nБорщ", "print_date": "2026-09-26"})
        self.assertTrue(status["exists"])
        self.assertEqual(status["display_name"], "26092026")
        self.assertEqual(MenuArchiveEntry.objects.count(), 1)

    def test_other_menu_type_is_not_a_conflict(self):
        MenuArchiveEntry.objects.create(
            menu_date=date(2026, 9, 26),
            menu_type="main",
            location_key="unknown_location",
            display_name="основное",
            relative_path="menu_archive/main.pdf",
            file_size=4,
        )
        status = archive_conflict_status({"ru": "Завтрак:\nКаша", "print_date": "2026-09-26"})
        self.assertFalse(status["exists"])


class EditorWriteGuardTests(TestCase):
    def test_bad_ru_does_not_archive(self):
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_user(
            username="editor-contract",
            password="pass",
            role="admin",
            must_change_password=False,
        )
        self.client.force_login(user)
        response = self.client.post(
            "/api/menu/pdf",
            data=json.dumps({"ru": 12, "print_date": "2026-09-26", "show_kcal": True}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "ru must be a string")
        self.assertEqual(MenuArchiveEntry.objects.count(), 0)
