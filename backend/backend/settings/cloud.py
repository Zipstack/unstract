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
    "plugins.subscription.time_trials.middleware.SubscriptionMiddleware",
    "middleware.exception.ExceptionLoggingMiddleware",
    "social_django.middleware.SocialAuthExceptionMiddleware",
]

SHARED_APPS = (
    # Multitenancy
    "django_tenants",
    "corsheaders",
    # For the organization model
    "account",
    # Django apps should go below this line
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.admindocs",
    # Third party apps should go below this line,
    "rest_framework",
    # Connector OAuth
    "connector_auth",
    "social_django",
    # Doc generator
    "drf_yasg",
    "docs",
    # Plugins
    "plugins",
    "log_events",
    "feature_flag",
    "django_celery_beat",
    "cloud",
)