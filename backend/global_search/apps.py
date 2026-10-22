from django.apps import AppConfig


class GlobalSearchConfig(AppConfig):
    name = "global_search"

    def ready(self) -> None:
        from global_search.oss_providers import OSS_PROVIDERS
        from global_search.registry import register_provider

        for provider_cls in OSS_PROVIDERS:
            register_provider(provider_cls())
