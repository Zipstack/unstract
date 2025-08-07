#!/usr/bin/env python3
"""Test script to validate worker configuration with different environment variable setups.
This script can be used to test configuration in development and production environments.
"""

import os
import sys

from shared.config import WorkerConfig


def print_config_section(title: str, config_dict: dict):
    """Print a configuration section with proper formatting."""
    print(f"\n{'='*60}")
    print(f" {title}")
    print(f"{'='*60}")

    for key, value in config_dict.items():
        if isinstance(value, str) and len(value) > 100:
            # Truncate very long values (like URLs)
            value = value[:97] + "..."
        print(f"{key:30} = {value}")


def test_default_config():
    """Test configuration with default values."""
    print("Testing DEFAULT configuration...")

    # Clear any existing environment variables
    env_vars_to_clear = [
        "CELERY_BACKEND_DB_HOST",
        "CELERY_BACKEND_DB_PORT",
        "CELERY_BACKEND_DB_NAME",
        "CELERY_BACKEND_DB_USER",
        "CELERY_BACKEND_DB_PASSWORD",
        "CELERY_BACKEND_DB_SCHEMA",
        "CACHE_REDIS_HOST",
        "CACHE_REDIS_PORT",
        "CACHE_REDIS_DB",
        "CACHE_REDIS_PASSWORD",
        "CACHE_REDIS_ENABLED",
        "INTERNAL_SERVICE_API_KEY",
    ]

    for var in env_vars_to_clear:
        if var in os.environ:
            del os.environ[var]

    # Set minimal required config
    os.environ["INTERNAL_SERVICE_API_KEY"] = "test_api_key"

    try:
        config = WorkerConfig()

        print_config_section(
            "Celery Backend Database",
            {
                "Host": config.celery_backend_db_host,
                "Port": config.celery_backend_db_port,
                "Database": config.celery_backend_db_name,
                "User": config.celery_backend_db_user,
                "Schema": config.celery_backend_db_schema,
                "Result Backend URL": config.celery_result_backend,
            },
        )

        cache_config = config.get_cache_redis_config()
        print_config_section("Redis Cache Configuration", cache_config)

        print("\n✅ Default configuration validated successfully!")
        return True

    except Exception as e:
        print(f"\n❌ Default configuration failed: {e}")
        return False


def test_production_config():
    """Test configuration with production-like environment variables."""
    print("\n\nTesting PRODUCTION configuration...")

    # Set production-like environment variables
    prod_env = {
        "CELERY_BACKEND_DB_HOST": "celery-db.example.com",
        "CELERY_BACKEND_DB_PORT": "5432",
        "CELERY_BACKEND_DB_NAME": "unstract_celery",
        "CELERY_BACKEND_DB_USER": "celery_user",
        "CELERY_BACKEND_DB_PASSWORD": "secure_celery_password",
        "CELERY_BACKEND_DB_SCHEMA": "celery_results",
        "CACHE_REDIS_ENABLED": "true",
        "CACHE_REDIS_HOST": "cache-redis.example.com",
        "CACHE_REDIS_PORT": "6379",
        "CACHE_REDIS_DB": "2",
        "CACHE_REDIS_PASSWORD": "secure_cache_password",
        "CACHE_REDIS_SSL": "true",
        "CELERY_BROKER_BASE_URL": "redis://broker-redis.example.com:6379/0",
        "INTERNAL_SERVICE_API_KEY": "prod_api_key_here",
        "INTERNAL_API_BASE_URL": "https://api.unstract.example.com/internal",
    }

    for key, value in prod_env.items():
        os.environ[key] = value

    try:
        config = WorkerConfig()

        print_config_section(
            "Celery Backend Database",
            {
                "Host": config.celery_backend_db_host,
                "Port": config.celery_backend_db_port,
                "Database": config.celery_backend_db_name,
                "User": config.celery_backend_db_user,
                "Schema": config.celery_backend_db_schema,
                "Result Backend URL": config.celery_result_backend,
            },
        )

        cache_config = config.get_cache_redis_config()
        print_config_section("Redis Cache Configuration", cache_config)

        print_config_section(
            "Other Settings",
            {
                "Broker URL": config.celery_broker_url,
                "API Base URL": config.internal_api_base_url,
                "Worker Name": config.worker_name,
            },
        )

        print("\n✅ Production configuration validated successfully!")
        return True

    except Exception as e:
        print(f"\n❌ Production configuration failed: {e}")
        return False


def test_disabled_cache_config():
    """Test configuration with Redis cache disabled."""
    print("\n\nTesting DISABLED CACHE configuration...")

    # Disable cache
    os.environ["CACHE_REDIS_ENABLED"] = "false"

    try:
        config = WorkerConfig()
        cache_config = config.get_cache_redis_config()

        print_config_section("Redis Cache Configuration (Disabled)", cache_config)

        if not cache_config.get("enabled"):
            print("\n✅ Disabled cache configuration validated successfully!")
            return True
        else:
            print("\n❌ Cache should be disabled but appears enabled")
            return False

    except Exception as e:
        print(f"\n❌ Disabled cache configuration failed: {e}")
        return False


def test_schema_configuration():
    """Test database schema configuration."""
    print("\n\nTesting SCHEMA configuration...")

    # Test custom schema
    os.environ["CELERY_BACKEND_DB_SCHEMA"] = "tenant_celery"
    os.environ["CACHE_REDIS_ENABLED"] = "true"

    try:
        config = WorkerConfig()

        print_config_section(
            "Schema Configuration",
            {
                "Schema": config.celery_backend_db_schema,
                "Result Backend URL": config.celery_result_backend,
            },
        )

        # Check if schema is properly included in URL
        if (
            "search_path" in config.celery_result_backend
            and "tenant_celery" in config.celery_result_backend
        ):
            print("\n✅ Schema configuration validated successfully!")
            return True
        else:
            print("\n❌ Schema not properly included in result backend URL")
            return False

    except Exception as e:
        print(f"\n❌ Schema configuration failed: {e}")
        return False


def main():
    """Run all configuration tests."""
    print("🚀 Worker Configuration Test Suite")
    print("=" * 60)

    tests = [
        ("Default Configuration", test_default_config),
        ("Production Configuration", test_production_config),
        ("Disabled Cache Configuration", test_disabled_cache_config),
        ("Schema Configuration", test_schema_configuration),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"\n❌ {test_name} crashed: {e}")
            failed += 1

    print(f"\n{'='*60}")
    print(" TEST RESULTS")
    print(f"{'='*60}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"📊 Total:  {passed + failed}")

    if failed == 0:
        print("\n🎉 All tests passed! Configuration is working correctly.")
        sys.exit(0)
    else:
        print("\n⚠️  Some tests failed. Please check the configuration.")
        sys.exit(1)


if __name__ == "__main__":
    main()
