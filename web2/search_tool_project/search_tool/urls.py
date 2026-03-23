from django.urls import path
from . import views

urlpatterns = [
    path("", views.IndexView.as_view(), name="index"),
    path("search/", views.SearchView.as_view(), name="search"),
    path("index/start/", views.StartIndexView.as_view(), name="start_index"),
    path("index/stop/", views.StopIndexView.as_view(), name="stop_index"),
    path("index/status/", views.IndexStatusView.as_view(), name="index_status"),
    path("index/summary/", views.IndexSummaryView.as_view(), name="index_summary"),
    path("index/unindexed/", views.IndexUnindexedView.as_view(), name="index_unindexed"),
    path("serve/", views.ServePdfView.as_view(), name="serve_pdf"),
    path("browse/", views.BrowseDirView.as_view(), name="browse_dir"),
    path("favorites/add/", views.AddFavoriteView.as_view(), name="add_favorite"),
    path("favorites/remove/", views.RemoveFavoriteView.as_view(), name="remove_favorite"),
    path("favorites/rename/", views.RenameFavoriteView.as_view(), name="rename_favorite"),
    path("favorites/move/", views.MoveFavoriteView.as_view(), name="move_favorite"),
    path("favorites/groups/create/", views.CreateGroupView.as_view(), name="create_group"),
    path("favorites/groups/delete/", views.DeleteGroupView.as_view(), name="delete_group"),
    path("favorites/groups/rename/", views.RenameGroupView.as_view(), name="rename_group"),
    path("admin/cleanup/preview/", views.CleanupPreviewView.as_view(), name="cleanup_preview"),
    path("admin/cleanup/execute/", views.CleanupExecuteView.as_view(), name="cleanup_execute"),
    path("admin/browse-roots/", views.GetBrowseRootsView.as_view(), name="get_browse_roots"),
    path("admin/browse-roots/add/", views.AddBrowseRootView.as_view(), name="add_browse_root"),
    path("admin/browse-roots/remove/", views.RemoveBrowseRootView.as_view(), name="remove_browse_root"),
]
