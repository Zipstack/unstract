"""Module for managing urls of traffic routing."""

from apps.traffic_routing.views import TrafficRuleListView
from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

traffic_rule = TrafficRuleListView.as_view({"get": TrafficRuleListView.get.__name__})

urlpatterns = format_suffix_patterns(
    [
        path("traffic_rules/", traffic_rule, name="traffic_rule"),
    ]
)
