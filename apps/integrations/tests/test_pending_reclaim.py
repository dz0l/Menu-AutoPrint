from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.integrations.models import IntegrationOperation
from apps.integrations.operations import PENDING_STALE_SECONDS, begin_operation


class PendingReclaimTests(TestCase):
    def test_stale_pending_is_reclaimed(self):
        op, replay = begin_operation(
            scope="default",
            kind=IntegrationOperation.KIND_CREATE_DISH,
            idempotency_key="k1",
            payload={"ru": "A"},
        )
        self.assertFalse(replay)
        IntegrationOperation.objects.filter(pk=op.pk).update(
            updated_at=timezone.now() - timedelta(seconds=PENDING_STALE_SECONDS + 5),
        )
        op2, replay2 = begin_operation(
            scope="default",
            kind=IntegrationOperation.KIND_CREATE_DISH,
            idempotency_key="k1",
            payload={"ru": "A"},
        )
        self.assertFalse(replay2)
        self.assertNotEqual(op.request_id, op2.request_id)

    def test_fresh_pending_stays_replay(self):
        op, _ = begin_operation(
            scope="default",
            kind=IntegrationOperation.KIND_CREATE_DISH,
            idempotency_key="k2",
            payload={"ru": "B"},
        )
        op2, replay = begin_operation(
            scope="default",
            kind=IntegrationOperation.KIND_CREATE_DISH,
            idempotency_key="k2",
            payload={"ru": "B"},
        )
        self.assertTrue(replay)
        self.assertEqual(op.request_id, op2.request_id)
