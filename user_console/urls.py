"""Phase 6 basic web console URL configuration."""

from django.urls import path

from .ajax_views import (
    ConsoleAjaxFileStatsView,
    ConsoleAjaxRecentFilesView,
    ConsoleAjaxSearchView,
)
from .batch_views import ConsoleBatchFileView
from .views import (
    ConsoleAdvancedFileListView,
    ConsoleDashboardView,
    ConsoleFileDeleteView,
    ConsoleFileDetailView,
    ConsoleFileDownloadView,
    ConsoleFileListView,
    ConsoleFilePreviewContentView,
    ConsoleFilePreviewView,
    ConsoleFileUploadView,
    ConsoleProfileView,
    ConsoleSupportContactView,
    ConsoleSupportHelpView,
    ConsoleSupportTermsView,
)

app_name = "user_console"

urlpatterns = [
    path("", ConsoleDashboardView.as_view(), name="dashboard"),
    path("profile/", ConsoleProfileView.as_view(), name="profile"),
    path(
        "support/contact/",
        ConsoleSupportContactView.as_view(),
        name="support_contact",
    ),
    path("support/help/", ConsoleSupportHelpView.as_view(), name="support_help"),
    path(
        "support/terms/",
        ConsoleSupportTermsView.as_view(),
        name="support_terms",
    ),
    path("files/", ConsoleFileListView.as_view(), name="file_list"),
    path("files/upload/", ConsoleFileUploadView.as_view(), name="file_upload"),
    path("files/batch/", ConsoleBatchFileView.as_view(), name="file_batch"),
    path(
        "files/advanced/",
        ConsoleAdvancedFileListView.as_view(),
        name="file_advanced",
    ),
    path(
        "files/search/",
        ConsoleAdvancedFileListView.as_view(),
        name="file_search",
    ),
    path(
        "files/<uuid:file_id>/",
        ConsoleFileDetailView.as_view(),
        name="file_detail",
    ),
    path(
        "files/<uuid:file_id>/download/",
        ConsoleFileDownloadView.as_view(),
        name="file_download",
    ),
    path(
        "files/<uuid:file_id>/preview/",
        ConsoleFilePreviewView.as_view(),
        name="file_preview",
    ),
    path(
        "files/<uuid:file_id>/preview/content/",
        ConsoleFilePreviewContentView.as_view(),
        name="file_preview_content",
    ),
    path(
        "files/<uuid:file_id>/delete/",
        ConsoleFileDeleteView.as_view(),
        name="file_delete",
    ),
    path(
        "ajax/file-stats/",
        ConsoleAjaxFileStatsView.as_view(),
        name="ajax_file_stats",
    ),
    path(
        "ajax/recent-files/",
        ConsoleAjaxRecentFilesView.as_view(),
        name="ajax_recent_files",
    ),
    path(
        "ajax/search/",
        ConsoleAjaxSearchView.as_view(),
        name="ajax_search",
    ),
]
