"""Configuration Dataclass Models

Enhanced configuration dataclasses for type-safe, validated worker configuration management.
These dataclasses complement the existing config.py patterns with stronger typing and validation.
"""

import os
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

# Import shared domain models from core
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../unstract/core/src"))
from unstract.core import serialize_dataclass_to_dict


class CacheBackend(Enum):
    """Supported cache backends."""

    REDIS = "redis"
    MEMORY = "memory"
    DISABLED = "disabled"


class LogLevel(Enum):
    """Supported log levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class PluginType(Enum):
    """Supported plugin types."""

    PROCESSOR = "processor"
    CONNECTOR = "connector"
    AUTHENTICATION = "authentication"
    MODIFIER = "modifier"
    QUEUES = "queues"
    SUBSCRIPTION = "subscription"


@dataclass
class CacheConfig:
    """Type-safe cache configuration with validation."""

    backend: CacheBackend
    enabled: bool = True
    default_ttl: int = 60  # seconds
    max_entries: int = 10000

    # Redis-specific configuration
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 1
    redis_password: str | None = None
    redis_username: str | None = None
    redis_ssl: bool = False
    redis_ssl_cert_reqs: str = "required"
    redis_url: str | None = None

    # Memory cache specific
    memory_max_size_mb: int = 256

    # TTL configurations for different cache types
    execution_status_ttl: int = 30
    pipeline_status_ttl: int = 60
    batch_summary_ttl: int = 90
    workflow_definition_ttl: int = 300

    def __post_init__(self):
        """Validate cache configuration after initialization."""
        if self.backend == CacheBackend.DISABLED:
            self.enabled = False
            return

        if not self.enabled:
            return

        errors = []

        # Validate TTL values
        if self.default_ttl <= 0:
            errors.append("default_ttl must be positive")
        if self.execution_status_ttl <= 0:
            errors.append("execution_status_ttl must be positive")
        if self.pipeline_status_ttl <= 0:
            errors.append("pipeline_status_ttl must be positive")
        if self.batch_summary_ttl <= 0:
            errors.append("batch_summary_ttl must be positive")
        if self.workflow_definition_ttl <= 0:
            errors.append("workflow_definition_ttl must be positive")

        # Redis-specific validation
        if self.backend == CacheBackend.REDIS:
            if not self.redis_host:
                errors.append("redis_host is required for Redis backend")
            if self.redis_port <= 0 or self.redis_port > 65535:
                errors.append("redis_port must be between 1 and 65535")
            if self.redis_db < 0:
                errors.append("redis_db must be non-negative")

        # Memory cache validation
        if self.backend == CacheBackend.MEMORY:
            if self.memory_max_size_mb <= 0:
                errors.append("memory_max_size_mb must be positive")
            if self.max_entries <= 0:
                errors.append("max_entries must be positive")

        if errors:
            raise ValueError(
                f"Cache configuration validation failed: {'; '.join(errors)}"
            )

    def get_redis_url(self) -> str:
        """Build Redis URL from configuration components."""
        if self.backend != CacheBackend.REDIS or not self.enabled:
            return ""

        if self.redis_url:
            return self.redis_url

        # Build Redis URL with authentication and SSL options
        scheme = "rediss" if self.redis_ssl else "redis"

        # Build authentication part
        auth_part = ""
        if self.redis_username and self.redis_password:
            auth_part = f"{self.redis_username}:{self.redis_password}@"
        elif self.redis_password:
            auth_part = f":{self.redis_password}@"

        # Build base URL
        url = f"{scheme}://{auth_part}{self.redis_host}:{self.redis_port}/{self.redis_db}"

        # Add SSL parameters if needed
        if self.redis_ssl and self.redis_ssl_cert_reqs != "required":
            url += f"?ssl_cert_reqs={self.redis_ssl_cert_reqs}"

        return url

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        return serialize_dataclass_to_dict(self)

    @classmethod
    def from_env(cls, prefix: str = "CACHE_") -> "CacheConfig":
        """Create cache configuration from environment variables."""
        backend_str = os.getenv(f"{prefix}BACKEND", "redis").lower()
        backend = CacheBackend.REDIS if backend_str == "redis" else CacheBackend.MEMORY

        if os.getenv(f"{prefix}REDIS_ENABLED", "true").lower() == "false":
            backend = CacheBackend.DISABLED

        return cls(
            backend=backend,
            enabled=os.getenv(f"{prefix}ENABLED", "true").lower() == "true",
            default_ttl=int(os.getenv(f"{prefix}DEFAULT_TTL", "60")),
            max_entries=int(os.getenv(f"{prefix}MAX_ENTRIES", "10000")),
            redis_host=os.getenv(f"{prefix}REDIS_HOST", "localhost"),
            redis_port=int(os.getenv(f"{prefix}REDIS_PORT", "6379")),
            redis_db=int(os.getenv(f"{prefix}REDIS_DB", "1")),
            redis_password=os.getenv(f"{prefix}REDIS_PASSWORD"),
            redis_username=os.getenv(f"{prefix}REDIS_USERNAME"),
            redis_ssl=os.getenv(f"{prefix}REDIS_SSL", "false").lower() == "true",
            redis_ssl_cert_reqs=os.getenv(f"{prefix}REDIS_SSL_CERT_REQS", "required"),
            redis_url=os.getenv(f"{prefix}REDIS_URL"),
            memory_max_size_mb=int(os.getenv(f"{prefix}MEMORY_MAX_SIZE_MB", "256")),
            execution_status_ttl=int(os.getenv(f"{prefix}EXECUTION_STATUS_TTL", "30")),
            pipeline_status_ttl=int(os.getenv(f"{prefix}PIPELINE_STATUS_TTL", "60")),
            batch_summary_ttl=int(os.getenv(f"{prefix}BATCH_SUMMARY_TTL", "90")),
            workflow_definition_ttl=int(
                os.getenv(f"{prefix}WORKFLOW_DEFINITION_TTL", "300")
            ),
        )


@dataclass
class PluginConfig:
    """Type-safe plugin configuration with validation."""

    plugin_id: str
    plugin_name: str
    plugin_type: PluginType
    enabled: bool = True
    version: str = "1.0.0"

    # Plugin-specific settings
    settings: dict[str, Any] = field(default_factory=dict)

    # Plugin loading configuration
    module_path: str | None = None
    class_name: str | None = None
    priority: int = 100  # Lower number = higher priority

    # Dependencies and requirements
    dependencies: list[str] = field(default_factory=list)
    required_env_vars: list[str] = field(default_factory=list)

    # Resource limits
    max_memory_mb: int = 512
    max_execution_time: int = 300  # seconds

    # Error handling
    retry_attempts: int = 3
    retry_backoff_factor: float = 1.5

    def __post_init__(self):
        """Validate plugin configuration after initialization."""
        errors = []

        # Required fields validation
        if not self.plugin_id:
            errors.append("plugin_id is required")
        if not self.plugin_name:
            errors.append("plugin_name is required")

        # Numeric validations
        if self.priority < 0:
            errors.append("priority must be non-negative")
        if self.max_memory_mb <= 0:
            errors.append("max_memory_mb must be positive")
        if self.max_execution_time <= 0:
            errors.append("max_execution_time must be positive")
        if self.retry_attempts < 0:
            errors.append("retry_attempts must be non-negative")
        if self.retry_backoff_factor <= 0:
            errors.append("retry_backoff_factor must be positive")

        # Module path validation
        if self.module_path and not self.class_name:
            errors.append("class_name is required when module_path is specified")

        # Check required environment variables
        if self.enabled:
            missing_env_vars = [
                var for var in self.required_env_vars if not os.getenv(var)
            ]
            if missing_env_vars:
                errors.append(
                    f"Missing required environment variables: {missing_env_vars}"
                )

        if errors:
            raise ValueError(
                f"Plugin configuration validation failed: {'; '.join(errors)}"
            )

    def is_loadable(self) -> bool:
        """Check if plugin can be loaded based on configuration."""
        if not self.enabled:
            return False

        # Check if module path exists
        if self.module_path:
            try:
                module_file = Path(self.module_path)
                if not module_file.exists():
                    return False
            except Exception:
                return False

        # Check required environment variables
        for var in self.required_env_vars:
            if not os.getenv(var):
                return False

        return True

    def get_import_path(self) -> str | None:
        """Get the full import path for the plugin."""
        if not self.module_path or not self.class_name:
            return None
        return f"{self.module_path}.{self.class_name}"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        return serialize_dataclass_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PluginConfig":
        """Create PluginConfig from dictionary data."""
        plugin_type_str = data.get("plugin_type", "processor")
        plugin_type = (
            PluginType(plugin_type_str)
            if isinstance(plugin_type_str, str)
            else plugin_type_str
        )

        return cls(
            plugin_id=data["plugin_id"],
            plugin_name=data["plugin_name"],
            plugin_type=plugin_type,
            enabled=data.get("enabled", True),
            version=data.get("version", "1.0.0"),
            settings=data.get("settings", {}),
            module_path=data.get("module_path"),
            class_name=data.get("class_name"),
            priority=data.get("priority", 100),
            dependencies=data.get("dependencies", []),
            required_env_vars=data.get("required_env_vars", []),
            max_memory_mb=data.get("max_memory_mb", 512),
            max_execution_time=data.get("max_execution_time", 300),
            retry_attempts=data.get("retry_attempts", 3),
            retry_backoff_factor=data.get("retry_backoff_factor", 1.5),
        )


@dataclass
class PluginRegistry:
    """Registry for managing multiple plugin configurations."""

    plugins: list[PluginConfig] = field(default_factory=list)
    enabled_only: bool = True

    def add_plugin(self, plugin: PluginConfig) -> None:
        """Add a plugin to the registry."""
        # Check for duplicate plugin IDs
        existing_ids = {p.plugin_id for p in self.plugins}
        if plugin.plugin_id in existing_ids:
            raise ValueError(f"Plugin with ID '{plugin.plugin_id}' already exists")

        self.plugins.append(plugin)

    def get_plugin(self, plugin_id: str) -> PluginConfig | None:
        """Get a plugin by ID."""
        for plugin in self.plugins:
            if plugin.plugin_id == plugin_id:
                return plugin
        return None

    def get_plugins_by_type(self, plugin_type: PluginType) -> list[PluginConfig]:
        """Get all plugins of a specific type."""
        plugins = [p for p in self.plugins if p.plugin_type == plugin_type]
        if self.enabled_only:
            plugins = [p for p in plugins if p.enabled]
        return sorted(plugins, key=lambda p: p.priority)

    def get_enabled_plugins(self) -> list[PluginConfig]:
        """Get all enabled plugins sorted by priority."""
        plugins = [p for p in self.plugins if p.enabled]
        return sorted(plugins, key=lambda p: p.priority)

    def get_loadable_plugins(self) -> list[PluginConfig]:
        """Get all plugins that can be loaded."""
        return [p for p in self.plugins if p.is_loadable()]

    def validate_dependencies(self) -> list[str]:
        """Validate plugin dependencies and return any errors."""
        errors = []
        plugin_ids = {p.plugin_id for p in self.plugins}

        for plugin in self.plugins:
            if not plugin.enabled:
                continue

            for dependency in plugin.dependencies:
                if dependency not in plugin_ids:
                    errors.append(
                        f"Plugin '{plugin.plugin_id}' depends on missing plugin '{dependency}'"
                    )
                else:
                    # Check if dependency is enabled
                    dep_plugin = self.get_plugin(dependency)
                    if dep_plugin and not dep_plugin.enabled:
                        errors.append(
                            f"Plugin '{plugin.plugin_id}' depends on disabled plugin '{dependency}'"
                        )

        return errors

    def to_dict(self) -> dict[str, Any]:
        """Convert registry to dictionary."""
        return {
            "plugins": [plugin.to_dict() for plugin in self.plugins],
            "enabled_only": self.enabled_only,
            "plugin_count": len(self.plugins),
            "enabled_count": len([p for p in self.plugins if p.enabled]),
            "loadable_count": len(self.get_loadable_plugins()),
        }

    @classmethod
    def from_config_dir(cls, config_dir: str | Path) -> "PluginRegistry":
        """Load plugin registry from configuration directory."""
        registry = cls()
        config_path = Path(config_dir)

        if not config_path.exists():
            return registry

        # Look for plugin configuration files
        for config_file in config_path.glob("plugin_*.json"):
            try:
                import json

                with open(config_file) as f:
                    plugin_data = json.load(f)

                if isinstance(plugin_data, list):
                    # Multiple plugins in one file
                    for plugin_dict in plugin_data:
                        plugin = PluginConfig.from_dict(plugin_dict)
                        registry.add_plugin(plugin)
                else:
                    # Single plugin in file
                    plugin = PluginConfig.from_dict(plugin_data)
                    registry.add_plugin(plugin)

            except Exception as e:
                # Log error but continue loading other plugins
                print(f"Error loading plugin config from {config_file}: {e}")

        return registry


@dataclass
class WorkerMetrics:
    """Configuration for worker metrics and monitoring."""

    enabled: bool = True
    collection_interval: int = 60  # seconds
    retention_days: int = 7

    # Metric types to collect
    collect_performance_metrics: bool = True
    collect_error_metrics: bool = True
    collect_queue_metrics: bool = True
    collect_resource_metrics: bool = True

    # Export configuration
    export_prometheus: bool = False
    export_statsd: bool = False
    export_cloudwatch: bool = False

    # Prometheus configuration
    prometheus_port: int = 8080
    prometheus_path: str = "/metrics"

    # StatsD configuration
    statsd_host: str = "localhost"
    statsd_port: int = 8125
    statsd_prefix: str = "unstract.worker"

    # CloudWatch configuration
    cloudwatch_namespace: str = "Unstract/Workers"
    cloudwatch_region: str = "us-east-1"

    def __post_init__(self):
        """Validate metrics configuration."""
        errors = []

        if self.collection_interval <= 0:
            errors.append("collection_interval must be positive")
        if self.retention_days <= 0:
            errors.append("retention_days must be positive")

        if self.export_prometheus:
            if self.prometheus_port <= 0 or self.prometheus_port > 65535:
                errors.append("prometheus_port must be between 1 and 65535")
            if not self.prometheus_path.startswith("/"):
                errors.append("prometheus_path must start with '/'")

        if self.export_statsd:
            if not self.statsd_host:
                errors.append("statsd_host is required for StatsD export")
            if self.statsd_port <= 0 or self.statsd_port > 65535:
                errors.append("statsd_port must be between 1 and 65535")

        if errors:
            raise ValueError(
                f"Metrics configuration validation failed: {'; '.join(errors)}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        return serialize_dataclass_to_dict(self)

    @classmethod
    def from_env(cls, prefix: str = "METRICS_") -> "WorkerMetrics":
        """Create metrics configuration from environment variables."""
        return cls(
            enabled=os.getenv(f"{prefix}ENABLED", "true").lower() == "true",
            collection_interval=int(os.getenv(f"{prefix}COLLECTION_INTERVAL", "60")),
            retention_days=int(os.getenv(f"{prefix}RETENTION_DAYS", "7")),
            collect_performance_metrics=os.getenv(
                f"{prefix}COLLECT_PERFORMANCE", "true"
            ).lower()
            == "true",
            collect_error_metrics=os.getenv(f"{prefix}COLLECT_ERROR", "true").lower()
            == "true",
            collect_queue_metrics=os.getenv(f"{prefix}COLLECT_QUEUE", "true").lower()
            == "true",
            collect_resource_metrics=os.getenv(
                f"{prefix}COLLECT_RESOURCE", "true"
            ).lower()
            == "true",
            export_prometheus=os.getenv(f"{prefix}EXPORT_PROMETHEUS", "false").lower()
            == "true",
            export_statsd=os.getenv(f"{prefix}EXPORT_STATSD", "false").lower() == "true",
            export_cloudwatch=os.getenv(f"{prefix}EXPORT_CLOUDWATCH", "false").lower()
            == "true",
            prometheus_port=int(os.getenv(f"{prefix}PROMETHEUS_PORT", "8080")),
            prometheus_path=os.getenv(f"{prefix}PROMETHEUS_PATH", "/metrics"),
            statsd_host=os.getenv(f"{prefix}STATSD_HOST", "localhost"),
            statsd_port=int(os.getenv(f"{prefix}STATSD_PORT", "8125")),
            statsd_prefix=os.getenv(f"{prefix}STATSD_PREFIX", "unstract.worker"),
            cloudwatch_namespace=os.getenv(
                f"{prefix}CLOUDWATCH_NAMESPACE", "Unstract/Workers"
            ),
            cloudwatch_region=os.getenv(f"{prefix}CLOUDWATCH_REGION", "us-east-1"),
        )


@dataclass
class SecurityConfig:
    """Security configuration for workers."""

    # API security
    require_api_key: bool = True
    api_key_header_name: str = "X-API-Key"

    # SSL/TLS configuration
    ssl_verify: bool = True
    ssl_cert_path: str | None = None
    ssl_key_path: str | None = None
    ssl_ca_path: str | None = None

    # Request validation
    max_request_size_mb: int = 100
    allowed_mime_types: list[str] = field(
        default_factory=lambda: [
            "application/pdf",
            "text/plain",
            "text/csv",
            "application/json",
        ]
    )

    # Rate limiting
    rate_limit_enabled: bool = False
    rate_limit_requests_per_minute: int = 100
    rate_limit_burst_size: int = 20

    # Content security
    sanitize_file_names: bool = True
    allow_external_urls: bool = False
    blocked_ip_ranges: list[str] = field(default_factory=list)

    def __post_init__(self):
        """Validate security configuration."""
        errors = []

        if self.max_request_size_mb <= 0:
            errors.append("max_request_size_mb must be positive")

        if self.rate_limit_enabled:
            if self.rate_limit_requests_per_minute <= 0:
                errors.append("rate_limit_requests_per_minute must be positive")
            if self.rate_limit_burst_size <= 0:
                errors.append("rate_limit_burst_size must be positive")

        # Validate SSL paths if provided
        if self.ssl_cert_path and not Path(self.ssl_cert_path).exists():
            errors.append(f"SSL certificate file not found: {self.ssl_cert_path}")
        if self.ssl_key_path and not Path(self.ssl_key_path).exists():
            errors.append(f"SSL key file not found: {self.ssl_key_path}")
        if self.ssl_ca_path and not Path(self.ssl_ca_path).exists():
            errors.append(f"SSL CA file not found: {self.ssl_ca_path}")

        if errors:
            raise ValueError(
                f"Security configuration validation failed: {'; '.join(errors)}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        return serialize_dataclass_to_dict(self)

    @classmethod
    def from_env(cls, prefix: str = "SECURITY_") -> "SecurityConfig":
        """Create security configuration from environment variables."""
        # Parse allowed MIME types from comma-separated string
        mime_types_str = os.getenv(f"{prefix}ALLOWED_MIME_TYPES", "")
        allowed_mime_types = (
            [mime.strip() for mime in mime_types_str.split(",") if mime.strip()]
            if mime_types_str
            else ["application/pdf", "text/plain", "text/csv", "application/json"]
        )

        # Parse blocked IP ranges
        ip_ranges_str = os.getenv(f"{prefix}BLOCKED_IP_RANGES", "")
        blocked_ip_ranges = (
            [ip.strip() for ip in ip_ranges_str.split(",") if ip.strip()]
            if ip_ranges_str
            else []
        )

        return cls(
            require_api_key=os.getenv(f"{prefix}REQUIRE_API_KEY", "true").lower()
            == "true",
            api_key_header_name=os.getenv(f"{prefix}API_KEY_HEADER_NAME", "X-API-Key"),
            ssl_verify=os.getenv(f"{prefix}SSL_VERIFY", "true").lower() == "true",
            ssl_cert_path=os.getenv(f"{prefix}SSL_CERT_PATH"),
            ssl_key_path=os.getenv(f"{prefix}SSL_KEY_PATH"),
            ssl_ca_path=os.getenv(f"{prefix}SSL_CA_PATH"),
            max_request_size_mb=int(os.getenv(f"{prefix}MAX_REQUEST_SIZE_MB", "100")),
            allowed_mime_types=allowed_mime_types,
            rate_limit_enabled=os.getenv(f"{prefix}RATE_LIMIT_ENABLED", "false").lower()
            == "true",
            rate_limit_requests_per_minute=int(
                os.getenv(f"{prefix}RATE_LIMIT_REQUESTS_PER_MINUTE", "100")
            ),
            rate_limit_burst_size=int(os.getenv(f"{prefix}RATE_LIMIT_BURST_SIZE", "20")),
            sanitize_file_names=os.getenv(f"{prefix}SANITIZE_FILE_NAMES", "true").lower()
            == "true",
            allow_external_urls=os.getenv(f"{prefix}ALLOW_EXTERNAL_URLS", "false").lower()
            == "true",
            blocked_ip_ranges=blocked_ip_ranges,
        )


# Utility functions for configuration management
def load_configuration_from_env(prefix: str = "") -> dict[str, Any]:
    """Load all configuration dataclasses from environment variables."""
    cache_prefix = f"{prefix}CACHE_" if prefix else "CACHE_"
    metrics_prefix = f"{prefix}METRICS_" if prefix else "METRICS_"
    security_prefix = f"{prefix}SECURITY_" if prefix else "SECURITY_"

    return {
        "cache": CacheConfig.from_env(cache_prefix),
        "metrics": WorkerMetrics.from_env(metrics_prefix),
        "security": SecurityConfig.from_env(security_prefix),
    }


def validate_all_configurations(configs: dict[str, Any]) -> list[str]:
    """Validate all configuration dataclasses and return any errors."""
    errors = []

    for config_name, config in configs.items():
        try:
            # Dataclasses with __post_init__ validation will raise ValueError
            if hasattr(config, "__post_init__"):
                config.__post_init__()
        except ValueError as e:
            errors.append(f"{config_name}: {str(e)}")
        except Exception as e:
            errors.append(f"{config_name}: Unexpected validation error: {str(e)}")

    return errors
