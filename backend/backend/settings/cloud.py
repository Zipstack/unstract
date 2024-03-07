from backend.settings.dev import *  # noqa: F401, F403


MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django_tenants.middleware.TenantSubfolderMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "account.custom_auth_middleware.CustomAuthMiddleware",
    "unstract-cloud.backend.plugins.subscription.time_trials.middleware.SubscriptionMiddleware"
    "middleware.exception.ExceptionLoggingMiddleware",
    "social_django.middleware.SocialAuthExceptionMiddleware",
]

TENANT_APPS = (
    # your tenant-specific apps
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "tenant_account",
    "project",
    "prompt",
    "connector",
    "adapter_processor",
    "file_management",
    "workflow_manager.endpoint",
    "workflow_manager.workflow",
    "tool_instance",
    "pipeline",
    "cron_expression_generator",
    "platform_settings",
    "api",
    "prompt_studio.prompt_profile_manager",
    "prompt_studio.prompt_studio",
    "prompt_studio.prompt_studio_core",
    "prompt_studio.prompt_studio_registry",
    "prompt_studio.prompt_studio_output_manager",
    "cloud",
)