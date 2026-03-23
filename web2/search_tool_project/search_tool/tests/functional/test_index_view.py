"""Functional tests for IndexView (GET /)."""
import pytest
from django.contrib.auth.models import User
from django.test import Client


@pytest.fixture
def user(db):
    return User.objects.create_user(username="testuser", password="pass")


@pytest.fixture
def client_logged_in(user):
    c = Client()
    c.login(username="testuser", password="pass")
    return c


@pytest.mark.django_db
class TestIndexView:
    def test_unauthenticated_redirects_to_login(self):
        c = Client()
        response = c.get("/")
        assert response.status_code == 302
        assert "/login/" in response["Location"]

    def test_authenticated_returns_200(self, client_logged_in):
        response = client_logged_in.get("/")
        assert response.status_code == 200

    def test_uses_correct_template(self, client_logged_in):
        response = client_logged_in.get("/")
        assert "search_tool/index.html" in [t.name for t in response.templates]

    def test_context_has_config(self, client_logged_in):
        response = client_logged_in.get("/")
        assert "config" in response.context

    def test_context_has_groups(self, client_logged_in):
        response = client_logged_in.get("/")
        assert "groups" in response.context

    def test_context_has_ungrouped_favorites(self, client_logged_in):
        response = client_logged_in.get("/")
        assert "ungrouped_favorites" in response.context
