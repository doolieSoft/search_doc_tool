"""Functional tests for favorites and group views."""
import json
import os

import pytest
from django.contrib.auth.models import User
from django.test import Client

from search_tool.models import Favorite, FavoriteGroup

FIXTURES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fixtures")


@pytest.fixture
def user(db):
    return User.objects.create_user(username="testuser", password="pass")


@pytest.fixture
def client_logged_in(user):
    c = Client()
    c.login(username="testuser", password="pass")
    return c


@pytest.mark.django_db
class TestAddFavoriteView:
    def test_unauthenticated_redirects(self):
        c = Client()
        response = c.post("/favorites/add/", {"folder": FIXTURES_DIR})
        assert response.status_code == 302

    def test_invalid_folder_redirects_to_index(self, client_logged_in):
        response = client_logged_in.post("/favorites/add/", {"folder": "/nonexistent/xyz"})
        assert response.status_code == 302

    def test_valid_folder_creates_favorite(self, client_logged_in, user):
        client_logged_in.post("/favorites/add/", {"folder": FIXTURES_DIR})
        assert Favorite.objects.filter(user=user, path=FIXTURES_DIR).exists()

    def test_valid_folder_redirects_to_index(self, client_logged_in):
        response = client_logged_in.post("/favorites/add/", {"folder": FIXTURES_DIR})
        assert response.status_code == 302
        assert response["Location"] == "/"


@pytest.mark.django_db
class TestRemoveFavoriteView:
    def test_removes_existing_favorite(self, client_logged_in, user):
        Favorite.objects.create(user=user, path=FIXTURES_DIR, name="Test")
        client_logged_in.post("/favorites/remove/", {"path": FIXTURES_DIR})
        assert not Favorite.objects.filter(user=user, path=FIXTURES_DIR).exists()

    def test_redirects_to_index(self, client_logged_in):
        response = client_logged_in.post("/favorites/remove/", {"path": "/some/path"})
        assert response.status_code == 302


@pytest.mark.django_db
class TestRenameFavoriteView:
    def test_rename_existing_favorite(self, client_logged_in, user):
        Favorite.objects.create(user=user, path=FIXTURES_DIR, name="OldName")
        response = client_logged_in.post("/favorites/rename/", {
            "path": FIXTURES_DIR, "name": "NewName"
        })
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data.get("ok") is True
        assert Favorite.objects.get(user=user, path=FIXTURES_DIR).name == "NewName"

    def test_missing_fields_returns_400(self, client_logged_in):
        response = client_logged_in.post("/favorites/rename/", {"path": ""})
        assert response.status_code == 400


@pytest.mark.django_db
class TestGroupViews:
    def test_create_group(self, client_logged_in, user):
        response = client_logged_in.post("/favorites/groups/create/", {"name": "MyGroup"})
        assert response.status_code == 200
        assert json.loads(response.content).get("ok") is True
        assert FavoriteGroup.objects.filter(user=user, name="MyGroup").exists()

    def test_create_group_missing_name_returns_400(self, client_logged_in):
        response = client_logged_in.post("/favorites/groups/create/", {"name": ""})
        assert response.status_code == 400

    def test_delete_group(self, client_logged_in, user):
        group = FavoriteGroup.objects.create(user=user, name="ToDelete")
        response = client_logged_in.post("/favorites/groups/delete/", {"group_id": group.pk})
        assert response.status_code == 200
        assert not FavoriteGroup.objects.filter(pk=group.pk).exists()

    def test_rename_group(self, client_logged_in, user):
        group = FavoriteGroup.objects.create(user=user, name="OldName")
        response = client_logged_in.post("/favorites/groups/rename/", {
            "group_id": group.pk, "name": "NewName"
        })
        assert response.status_code == 200
        assert FavoriteGroup.objects.get(pk=group.pk).name == "NewName"

    def test_rename_group_missing_fields_returns_400(self, client_logged_in):
        response = client_logged_in.post("/favorites/groups/rename/", {"group_id": "", "name": ""})
        assert response.status_code == 400
