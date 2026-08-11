"""File REST URL configuration through Phase 5."""

from django.urls import path

from .views import (
    FileDetailView,
    FileDownloadView,
    FileListView,
    FileUploadView,
    MyFilesView,
)

app_name = "file_api"

urlpatterns = [
    path("", FileListView.as_view(), name="list"),
    path("upload/", FileUploadView.as_view(), name="upload"),
    path("my-files/", MyFilesView.as_view(), name="my_files"),
    path("<uuid:file_id>/", FileDetailView.as_view(), name="detail"),
    path("<uuid:file_id>/download/", FileDownloadView.as_view(), name="download"),
]
