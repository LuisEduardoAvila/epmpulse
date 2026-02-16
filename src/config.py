"""Configuration management for EPMPulse.

Loads configuration from environment variables and optional YAML file.
All secrets come from environment variables only.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Any, List

try:
    import yaml
except ImportError:
    yaml = None


def get_api_key() -> str:
    """Get API key from environment.
    
    Returns:
        API key string
        
    Raises:
        ValueError: If API key is not set
    """
    api_key = os.environ.get('EPMPULSE_API_KEY')
    if not api_key:
        raise ValueError(
            "EPMPULSE_API_KEY environment variable is required"
        )
    return api_key


def get_config() -> Dict[str, Any]:
    """Load configuration from apps.json.
    
    Returns:
        Configuration dictionary
        
    Raises:
        ValueError: If canvas ID contains placeholder
    """
    config_file = Path(__file__).parent.parent / "config" / "apps.json"
    if config_file.exists():
        try:
            import json
            with open(config_file, 'r') as f:
                config = json.load(f)
            
            # Validate canvas IDs don't contain placeholders
            validate_canvas_ids(config)
            
            return config
        except Exception:
            pass
    return {}


def validate_canvas_ids(config: Dict[str, Any]) -> None:
    """Validate that canvas IDs don't contain placeholder values.
    
    Args:
        config: Configuration dictionary
        
    Raises:
        ValueError: If a canvas ID contains a placeholder
    """
    channels = config.get('channels', {})
    for channel_id, channel_config in channels.items():
        canvas_id = channel_config.get('canvas_id', '')
        if 'placeholder' in canvas_id.lower():
            raise ValueError(
                f"Canvas ID for channel {channel_id} contains placeholder. "
                f"Set {channel_config.get('canvas_env', 'SLACK_MAIN_CANVAS_ID')} environment variable."
            )
        # Also check for ${...} pattern that wasn't substituted
        if canvas_id.startswith('${') and canvas_id.endswith('}'):
            raise ValueError(
                f"Canvas ID for channel {channel_id} is an unsubstituted template: {canvas_id}. "
                f"Set the corresponding environment variable."
            )


def get_app_config(app_name: str) -> Optional[Dict[str, Any]]:
    """Get configuration for specific app.
    
    Args:
        app_name: Application name
        
    Returns:
        App configuration or None if not found
    """
    config = get_config()
    return config.get('apps', {}).get(app_name)


@dataclass
class SlackConfig:
    """Slack integration configuration."""

    bot_token: str
    main_channel_id: str
    main_canvas_id: Optional[str] = None
    arcs_channel_id: Optional[str] = None
    arcs_canvas_id: Optional[str] = None

    # Rate limiting
    min_update_interval_sec: int = 2
    max_retries: int = 3
    retry_backoff_sec: list = field(default_factory=lambda: [1, 2, 4])

    @classmethod
    def from_env(cls) -> "SlackConfig":
        """Load Slack configuration from environment variables."""
        return cls(
            bot_token=os.environ.get("SLACK_BOT_TOKEN", ""),
            main_channel_id=os.environ.get("SLACK_MAIN_CHANNEL_ID", ""),
            main_canvas_id=os.environ.get("SLACK_MAIN_CANVAS_ID"),
            arcs_channel_id=os.environ.get("SLACK_ARCS_CHANNEL_ID"),
            arcs_canvas_id=os.environ.get("SLACK_ARCS_CANVAS_ID"),
        )


@dataclass
class APIConfig:
    """API server configuration."""

    host: str = "0.0.0.0"
    port: int = 18800
    debug: bool = False
    api_key: str = ""

    # Rate limiting
    rate_limit_post: str = "60 per minute"
    rate_limit_get: str = "100 per minute"

    @classmethod
    def from_env(cls) -> "APIConfig":
        """Load API configuration from environment variables."""
        return cls(
            host=os.environ.get("EPMPULSE_HOST", "0.0.0.0"),
            port=int(os.environ.get("EPMPULSE_PORT", "18800")),
            debug=os.environ.get("EPMPULSE_DEBUG", "false").lower() == "true",
            api_key=os.environ.get("EPMPULSE_API_KEY", ""),
        )


@dataclass
class StateConfig:
    """State management configuration."""

    state_file: Path = field(default_factory=lambda: Path("data/apps_status.json"))
    lock_file: Path = field(default_factory=lambda: Path("data/apps_status.lock"))
    backup_dir: Path = field(default_factory=lambda: Path("data/backups"))
    apps_config_file: Path = field(
        default_factory=lambda: Path("config/apps.json")
    )

    # Stale job detection
    stale_loading_timeout_hours: int = 2

    @classmethod
    def from_env(cls) -> "StateConfig":
        """Load state configuration from environment variables."""
        base_dir = os.environ.get("EPMPULSE_DATA_DIR", "data")
        data_path = Path(base_dir)

        return cls(
            state_file=data_path / "apps_status.json",
            lock_file=data_path / "apps_status.lock",
            backup_dir=data_path / "backups",
            apps_config_file=Path(
                os.environ.get("EPMPULSE_APPS_CONFIG", "config/apps.json")
            ),
        )


@dataclass
class LoggingConfig:
    """Logging configuration."""

    level: str = "INFO"
    format: str = "json"
    file: Optional[str] = None

    @classmethod
    def from_env(cls) -> "LoggingConfig":
        """Load logging configuration from environment variables."""
        return cls(
            level=os.environ.get("EPMPULSE_LOG_LEVEL", "INFO"),
            format=os.environ.get("EPMPULSE_LOG_FORMAT", "json"),
            file=os.environ.get("EPMPULSE_LOG_FILE"),
        )


@dataclass
class Config:
    """Main configuration container."""

    api: APIConfig
    slack: SlackConfig
    state: StateConfig
    logging: LoggingConfig

    # Runtime settings
    environment: str = "development"

    @classmethod
    def from_env(cls) -> "Config":
        """Load all configuration from environment variables."""
        return cls(
            api=APIConfig.from_env(),
            slack=SlackConfig.from_env(),
            state=StateConfig.from_env(),
            logging=LoggingConfig.from_env(),
            environment=os.environ.get("EPMPULSE_ENV", "development"),
        )

    @classmethod
    def from_yaml(cls, path: str) -> "Config":
        """Load configuration from YAML file, env vars override."""
        config_path = Path(path)

        if config_path.exists():
            with open(config_path, "r") as f:
                yaml_config = yaml.safe_load(f) or {}
        else:
            yaml_config = {}

        # Start with env-based config
        config = cls.from_env()

        # Override with YAML values (env vars take precedence)
        if "api" in yaml_config:
            config.api.host = yaml_config["api"].get("host", config.api.host)
            config.api.port = yaml_config["api"].get("port", config.api.port)
            config.api.debug = yaml_config["api"].get("debug", config.api.debug)

        if "slack" in yaml_config:
            config.slack.min_update_interval_sec = yaml_config["slack"].get(
                "min_update_interval_sec", config.slack.min_update_interval_sec
            )

        if "state" in yaml_config:
            config.state.stale_loading_timeout_hours = yaml_config["state"].get(
                "stale_loading_timeout_hours",
                config.state.stale_loading_timeout_hours,
            )

        if "logging" in yaml_config:
            config.logging.level = yaml_config["logging"].get(
                "level", config.logging.level
            )

        return config

    def validate(self) -> list[str]:
        """Validate configuration and return list of errors."""
        errors = []

        if not self.api.api_key:
            errors.append("EPMPULSE_API_KEY is required")

        if not self.slack.bot_token:
            errors.append("SLACK_BOT_TOKEN is required")

        if not self.slack.main_channel_id:
            errors.append("SLACK_MAIN_CHANNEL_ID is required")

        return errors