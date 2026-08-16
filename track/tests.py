import datetime
import uuid
from unittest import mock

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.utils import timezone
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from core.auth import SupabaseJWTAuthentication, SupabaseUser
from .models import Budget, Category, Expense


def make_rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    return private_pem, public_pem


class FakeSigningKey:
    """Mimics jwt.PyJWK so SupabaseJWTAuthentication._verify can read .key."""

    def __init__(self, public_pem):
        self.key = public_pem


class SupabaseJWTAuthenticationTests(TestCase):
    def setUp(self):
        self.private_pem, self.public_pem = make_rsa_keypair()
        self.user_id = str(uuid.uuid4())
        self.factory = APIRequestFactory()

    def _token(self, *, sub=None, exp_offset=3600, aud="authenticated"):
        now = timezone.now().timestamp()
        return jwt.encode(
            {
                "sub": sub or self.user_id,
                "email": "user@example.com",
                "aud": aud,
                "exp": now + exp_offset,
                "iss": "https://demo.supabase.co/auth/v1",
            },
            self.private_pem,
            algorithm="RS256",
        )

    def test_valid_token_authenticates(self):
        request = self.factory.get(
            "/", HTTP_AUTHORIZATION="Bearer " + self._token()
        )
        with mock.patch(
            "core.auth._get_jwks_client",
            return_value=type(
                "FakeClient",
                (),
                {"get_signing_key_from_jwt": lambda s, t: FakeSigningKey(self.public_pem)},
            )(),
        ):
            user, token = SupabaseJWTAuthentication().authenticate(request)
        self.assertEqual(user.id, self.user_id)
        self.assertEqual(user.email, "user@example.com")
        self.assertTrue(user.is_authenticated)

    def test_missing_header_is_anonymous(self):
        request = self.factory.get("/")
        self.assertIsNone(SupabaseJWTAuthentication().authenticate(request))

    def test_expired_token_rejected(self):
        request = self.factory.get(
            "/", HTTP_AUTHORIZATION="Bearer " + self._token(exp_offset=-3600)
        )
        with mock.patch(
            "core.auth._get_jwks_client",
            return_value=type(
                "FakeClient",
                (),
                {"get_signing_key_from_jwt": lambda s, t: FakeSigningKey(self.public_pem)},
            )(),
        ):
            from rest_framework.exceptions import AuthenticationFailed

            with self.assertRaises(AuthenticationFailed):
                SupabaseJWTAuthentication().authenticate(request)

    def test_garbage_token_rejected(self):
        request = self.factory.get("/", HTTP_AUTHORIZATION="Bearer not-a-jwt")
        with mock.patch(
            "core.auth._get_jwks_client",
            return_value=type(
                "FakeClient",
                (),
                {"get_signing_key_from_jwt": lambda s, t: FakeSigningKey(self.public_pem)},
            )(),
        ):
            from rest_framework.exceptions import AuthenticationFailed

            with self.assertRaises(AuthenticationFailed):
                SupabaseJWTAuthentication().authenticate(request)


class TrackApiTests(TestCase):
    def setUp(self):
        self.user_a = str(uuid.uuid4())
        self.user_b = str(uuid.uuid4())
        # Categories are seeded by migration 0002 — reuse those rows.
        self.food, _ = Category.objects.get_or_create(name="Food", defaults={"kind": "expense"})
        self.rent, _ = Category.objects.get_or_create(name="Rent", defaults={"kind": "expense"})
        self.income_cat, _ = Category.objects.get_or_create(name="Income", defaults={"kind": "income"})

        self.client = APIClient()
        self.client.force_authenticate(user=SupabaseUser(id=self.user_a))

    def _add_expense(self, amount, category=None, type="expense", date=None):
        payload = {"amount": amount, "type": type, "category": category}
        if date:
            payload["date"] = date.isoformat()
        return self.client.post("/api/expenses/", payload, format="json")

    def test_create_and_list_expense(self):
        res = self._add_expense(250.50, self.food.id)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)

        listed = self.client.get("/api/expenses/")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.data), 1)
        self.assertEqual(float(listed.data[0]["amount"]), 250.50)
        self.assertEqual(listed.data[0]["category_name"], "Food")

    def test_negative_amount_rejected(self):
        res = self._add_expense(-5, self.food.id)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_ownership_isolation(self):
        self._add_expense(100, self.food.id)
        other = APIClient()
        other.force_authenticate(user=SupabaseUser(id=self.user_b))
        listed = other.get("/api/expenses/")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.data, [])
        # user B cannot touch user A's expense by id
        expense = Expense.objects.get(user_id=self.user_a)
        res = other.delete(f"/api/expenses/{expense.id}/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_budget_spent_recomputes_live(self):
        # create budget first (spent = 0)
        res = self.client.post(
            "/api/budgets/",
            {"category": self.food.id, "monthly_limit": 1000},
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(float(res.data["spent"]), 0)

        # add an expense → spent follows
        self._add_expense(300, self.food.id)
        self._add_expense(150.50, self.food.id)
        budget = Budget.objects.get(user_id=self.user_a, category=self.food)
        self.assertEqual(float(budget.spent), 450.50)

        # delete an expense → spent drops
        expense = Expense.objects.get(user_id=self.user_a, amount=300)
        self.client.delete(f"/api/expenses/{expense.id}/")
        budget.refresh_from_db()
        self.assertEqual(float(budget.spent), 150.50)

        # dashboard flags over-budget
        self.client.patch(
            f"/api/budgets/{budget.id}/", {"monthly_limit": 100}, format="json"
        )
        dash = self.client.get("/api/dashboard/").data
        row = dash["budgets"][0]
        self.assertTrue(row["over"])
        self.assertEqual(float(row["spent"]), 150.50)

    def test_dashboard_aggregates(self):
        today = timezone.localdate()
        self._add_expense(500, self.food.id, date=today)
        self._add_expense(200, self.rent.id, date=today)
        self._add_expense(1000, self.income_cat.id, type="income", date=today)

        dash = self.client.get("/api/dashboard/").data
        self.assertEqual(dash["month"], today.strftime("%B %Y"))
        self.assertEqual(float(dash["spent_total"]), 700)
        self.assertEqual(float(dash["income_total"]), 1000)
        self.assertEqual(float(dash["net"]), 300)
        self.assertEqual(len(dash["trend"]), 6)
        self.assertEqual(dash["trend"][-1]["label"], today.strftime("%b %Y"))
        by_cat = {c["name"]: c["total"] for c in dash["spent_by_category"]}
        self.assertEqual(by_cat, {"Food": 500.0, "Rent": 200.0})

    def test_unauthorized_requests_are_401(self):
        anon = APIClient()
        res = anon.get("/api/expenses/")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_edit_expense(self):
        res = self._add_expense(100, self.food.id)
        expense_id = res.data["id"]
        patched = self.client.patch(
            f"/api/expenses/{expense_id}/",
            {"amount": 80, "category": self.rent.id, "note": "edited"},
            format="json",
        )
        self.assertEqual(patched.status_code, 200)
        self.assertEqual(float(patched.data["amount"]), 80)
        self.assertEqual(patched.data["category_name"], "Rent")
        self.assertEqual(patched.data["note"], "edited")

    def test_categories_are_public(self):
        res = APIClient().get("/api/categories/")
        self.assertEqual(res.status_code, 200)
        names = [c["name"] for c in res.data]
        self.assertIn("Food", names)
