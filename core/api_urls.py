"""Core service API routes."""

from django.urls import path

from .api_views import AggregateStatisticsView, ApiDiscoveryView, HealthCheckView

app_name = "core_api"

urlpatterns = [
    path("", ApiDiscoveryView.as_view(), name="discovery"),
    path("health/", HealthCheckView.as_view(), name="health"),
    path("statistics/", AggregateStatisticsView.as_view(), name="statistics"),
]
