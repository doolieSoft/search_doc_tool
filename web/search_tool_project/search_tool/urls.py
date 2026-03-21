from django.urls import path
from . import views

urlpatterns = [
    path("", views.index_view, name="index"),
    path("search/", views.search_view, name="search"),
    path("index/start/", views.start_index, name="start_index"),
    path("index/stop/", views.stop_index, name="stop_index"),
    path("index/status/", views.index_status, name="index_status"),
    path("index/summary/", views.index_summary, name="index_summary"),
    path("index/unindexed/", views.index_unindexed, name="index_unindexed"),
    path("serve/", views.serve_pdf, name="serve_pdf"),
    path("browse/", views.browse_dir, name="browse_dir"),
    path("favorites/add/", views.add_favorite, name="add_favorite"),
    path("favorites/remove/", views.remove_favorite, name="remove_favorite"),
    path("favorites/rename/", views.rename_favorite, name="rename_favorite"),
    path("favorites/move/", views.move_favorite, name="move_favorite"),
    path("favorites/groups/create/", views.create_group, name="create_group"),
    path("favorites/groups/delete/", views.delete_group, name="delete_group"),
    path("favorites/groups/rename/", views.rename_group, name="rename_group"),
]
