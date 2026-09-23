from __future__ import annotations

from io import BytesIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from apps.dishes.models import Dish
from apps.integrations.auth import generate_api_key, hash_api_key
from apps.menu.covers import create_cover
from apps.menu.models import MenuCover


User = get_user_model()


@override_settings(
    INTEGRATION_API_ENABLED=True,
    INTEGRATION_OPERATION_TTL_HOURS=24,
    MEDIA_ROOT=None,  # set in setUp
)
class IntegrationApiTests(TestCase):
    def setUp(self):
        self.media = Path(self._media_dir())
        self.media.mkdir(parents=True, exist_ok=True)
        self.override = override_settings(MEDIA_ROOT=str(self.media))
        self.override.enable()
        self.addCleanup(self.override.disable)

        self.service = User.objects.create_user(
            username="integration-service",
            password="Unused!Pass1",
            role=User.Role.ADMIN,
            is_staff=False,
            is_superuser=False,
            must_change_password=False,
        )
        self.raw_key = generate_api_key()
        self.key_hash = hash_api_key(self.raw_key)
        settings_override = override_settings(
            INTEGRATION_API_ENABLED=True,
            INTEGRATION_SERVICE_USER_ID=self.service.id,
            INTEGRATION_API_KEY_HASH=self.key_hash,
            MEDIA_ROOT=str(self.media),
        )
        settings_override.enable()
        self.addCleanup(settings_override.disable)

        self.client = Client()
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

        self.dish = Dish.objects.create(
            name_ru="Борщ",
            name_en="Borscht",
            grams_default=250,
            kcal_per_100=45,
            category_ru="Супы",
            category_en="Soups",
        )
        self.incomplete = Dish.objects.create(
            name_ru="Котлета",
            name_en="",
            grams_default=None,
            kcal_per_100=None,
        )
        self.cover = self._make_cover()

    def _media_dir(self) -> str:
        return str(Path(__file__).resolve().parent / "_test_media" / self.id().replace(".", "_"))

    def _make_cover(self) -> MenuCover:
        image = Image.new("RGB", (40, 40), color=(200, 100, 50))
        buf = BytesIO()
        image.save(buf, format="PNG")
        uploaded = SimpleUploadedFile("cover.png", buf.getvalue(), content_type="image/png")
        return create_cover(location_name="Тест", uploaded=uploaded, user=self.service)

    def test_requires_bearer(self):
        response = self.client.get("/api/integration/v1/capabilities")
        self.assertEqual(response.status_code, 401)

    def test_capabilities(self):
        response = self.client.get("/api/integration/v1/capabilities", **self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["contract_version"], "1")

    def test_session_user_cannot_use_integration_without_bearer(self):
        editor = User.objects.create_user(
            username="editor",
            password="Editor!Pass1",
            role=User.Role.ADMIN,
            must_change_password=False,
        )
        self.client.force_login(editor)
        response = self.client.get("/api/integration/v1/capabilities")
        self.assertEqual(response.status_code, 401)

    def test_menu_check_ready_and_incomplete(self):
        ok = self.client.post(
            "/api/integration/v1/menu/check",
            data={"ru": "Супы:\nБорщ", "show_kcal": True},
            content_type="application/json",
            **self.auth,
        )
        self.assertEqual(ok.status_code, 200)
        body = ok.json()
        self.assertTrue(body["ready"])

        bad = self.client.post(
            "/api/integration/v1/menu/check",
            data={"ru": "Котлета", "show_kcal": True},
            content_type="application/json",
            **self.auth,
        )
        self.assertEqual(bad.status_code, 200)
        self.assertFalse(bad.json()["ready"])
        self.assertIn("en", bad.json()["lines"][0]["missing_fields"])

    def test_create_and_fill_dish(self):
        created = self.client.post(
            "/api/integration/v1/dishes",
            data={"ru": "Новое блюдо", "en": "", "gr": None, "kcal": None, "catRu": "Супы"},
            content_type="application/json",
            HTTP_AUTHORIZATION=self.auth["HTTP_AUTHORIZATION"],
            HTTP_IDEMPOTENCY_KEY="create-1",
        )
        self.assertEqual(created.status_code, 201)
        dish_id = created.json()["id"]
        version = created.json()["version"]

        filled = self.client.patch(
            f"/api/integration/v1/dishes/{dish_id}/missing-fields",
            data={"version": version, "en": "New dish", "gr": 100, "kcal": 50},
            content_type="application/json",
            **self.auth,
        )
        self.assertEqual(filled.status_code, 200)
        self.assertEqual(filled.json()["en"], "New dish")

        conflict = self.client.patch(
            f"/api/integration/v1/dishes/{dish_id}/missing-fields",
            data={"version": version, "en": "Other"},
            content_type="application/json",
            **self.auth,
        )
        self.assertEqual(conflict.status_code, 409)

        replay = self.client.post(
            "/api/integration/v1/dishes",
            data={"ru": "Новое блюдо", "en": "", "gr": None, "kcal": None, "catRu": "Супы"},
            content_type="application/json",
            HTTP_AUTHORIZATION=self.auth["HTTP_AUTHORIZATION"],
            HTTP_IDEMPOTENCY_KEY="create-1",
        )
        self.assertEqual(replay.status_code, 201)
        self.assertEqual(replay.json()["id"], dish_id)

    def test_pdf_requires_ready_menu_and_is_idempotent(self):
        payload = {
            "ru": "Супы:\nБорщ",
            "print_date": "2026-09-22",
            "cover_id": self.cover.id,
            "show_kcal": True,
            "auto_format": True,
        }
        first = self.client.post(
            "/api/integration/v1/menu/pdf",
            data=payload,
            content_type="application/json",
            HTTP_AUTHORIZATION=self.auth["HTTP_AUTHORIZATION"],
            HTTP_IDEMPOTENCY_KEY="pdf-1",
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first["Content-Type"], "application/pdf")
        pdf_bytes = first.content
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

        second = self.client.post(
            "/api/integration/v1/menu/pdf",
            data=payload,
            content_type="application/json",
            HTTP_AUTHORIZATION=self.auth["HTTP_AUTHORIZATION"],
            HTTP_IDEMPOTENCY_KEY="pdf-1",
        )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.content, pdf_bytes)

        incomplete = self.client.post(
            "/api/integration/v1/menu/pdf",
            data={
                "ru": "Котлета",
                "print_date": "2026-09-22",
                "cover_id": self.cover.id,
                "show_kcal": True,
                "auto_format": True,
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=self.auth["HTTP_AUTHORIZATION"],
            HTTP_IDEMPOTENCY_KEY="pdf-bad",
        )
        self.assertEqual(incomplete.status_code, 422)

    def test_covers_and_categories(self):
        covers = self.client.get("/api/integration/v1/covers", **self.auth)
        self.assertEqual(covers.status_code, 200)
        self.assertTrue(covers.json()["items"])

        image = self.client.get(f"/api/integration/v1/covers/{self.cover.id}/image", **self.auth)
        self.assertEqual(image.status_code, 200)

        cats = self.client.get("/api/integration/v1/categories", **self.auth)
        self.assertEqual(cats.status_code, 200)
        self.assertTrue(any(item["catRu"] == "Супы" for item in cats.json()["items"]))
