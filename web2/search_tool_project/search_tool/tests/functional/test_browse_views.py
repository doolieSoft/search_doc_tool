"""Functional tests for BrowseDirView and browse root admin views."""
import json
import os

import pytest
from django.contrib.auth.models import User
from django.test import Client

from search_tool.models import BrowseRoot

FIXTURES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fixtures")


@pytest.fixture
def user(db):
    return User.objects.create_user(username="testuser", password="pass")


@pytest.fixture
def superuser(db):
    return User.objects.create_superuser(username="admin", password="adminpass")


@pytest.fixture
def client_logged_in(user):
    c = Client()
    c.login(username="testuser", password="pass")
    return c


@pytest.fixture
def client_superuser(superuser):
    c = Client()
    c.login(username="admin", password="adminpass")
    return c


@pytest.mark.django_db
class TestBrowseDirView:
    def test_unauthenticated_redirects(self):
        c = Client()
        response = c.get("/browse/")
        assert response.status_code == 302

    def test_no_roots_non_superuser_returns_503(self, client_logged_in):
        response = client_logged_in.get("/browse/")
        assert response.status_code == 503
        data = json.loads(response.content)
        assert "error" in data

    def test_superuser_no_roots_no_path_returns_drives(self, client_superuser):
        response = client_superuser.get("/browse/")
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["mode"] == "drives"
        assert isinstance(data["entries"], list)

    def test_with_root_configured_no_path_returns_roots(self, client_logged_in):
        BrowseRoot.objects.create(label="Fixtures", path=FIXTURES_DIR)
        response = client_logged_in.get("/browse/")
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["mode"] == "roots"
        assert any(e["path"] == FIXTURES_DIR for e in data["entries"])

    def test_path_outside_root_returns_403(self, client_logged_in):
        BrowseRoot.objects.create(label="Fixtures", path=FIXTURES_DIR)
        response = client_logged_in.get("/browse/", {"path": "/some/other/path"})
        assert response.status_code == 403


@pytest.mark.django_db
class TestGetBrowseRootsView:
    def test_non_superuser_returns_403(self, client_logged_in):
        response = client_logged_in.get("/admin/browse-roots/")
        assert response.status_code == 403

    def test_superuser_returns_roots_list(self, client_superuser):
        BrowseRoot.objects.create(label="Test", path=FIXTURES_DIR)
        response = client_superuser.get("/admin/browse-roots/")
        assert response.status_code == 200
        data = json.loads(response.content)
        assert "roots" in data
        assert any(r["path"] == FIXTURES_DIR for r in data["roots"])


@pytest.mark.django_db
class TestAddBrowseRootView:
    def test_non_superuser_returns_403(self, client_logged_in):
        response = client_logged_in.post("/admin/browse-roots/add/", {
            "path": FIXTURES_DIR, "label": "Test"
        })
        assert response.status_code == 403

    def test_missing_fields_returns_400(self, client_superuser):
        response = client_superuser.post("/admin/browse-roots/add/", {"path": ""})
        assert response.status_code == 400

    def test_nonexistent_path_returns_400(self, client_superuser):
        response = client_superuser.post("/admin/browse-roots/add/", {
            "path": "/nonexistent/xyz", "label": "Test"
        })
        assert response.status_code == 400

    def test_valid_creates_root(self, client_superuser):
        response = client_superuser.post("/admin/browse-roots/add/", {
            "path": FIXTURES_DIR, "label": "Fixtures"
        })
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data.get("ok") is True
        assert BrowseRoot.objects.filter(path=FIXTURES_DIR).exists()

    def test_duplicate_returns_400(self, client_superuser):
        BrowseRoot.objects.create(label="Fixtures", path=FIXTURES_DIR)
        response = client_superuser.post("/admin/browse-roots/add/", {
            "path": FIXTURES_DIR, "label": "Fixtures2"
        })
        assert response.status_code == 400


@pytest.mark.django_db
class TestRemoveBrowseRootView:
    def test_non_superuser_returns_403(self, client_logged_in):
        root = BrowseRoot.objects.create(label="Test", path=FIXTURES_DIR)
        response = client_logged_in.post("/admin/browse-roots/remove/", {"id": root.pk})
        assert response.status_code == 403

    def test_superuser_removes_root(self, client_superuser):
        root = BrowseRoot.objects.create(label="Test", path=FIXTURES_DIR)
        response = client_superuser.post("/admin/browse-roots/remove/", {"id": root.pk})
        assert response.status_code == 200
        assert not BrowseRoot.objects.filter(pk=root.pk).exists()
