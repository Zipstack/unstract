from django.apps import AppConfig


class AppDeploymentConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "pluggable_apps.apps.app_deployment"
