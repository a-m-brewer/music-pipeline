import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class PathsConfig:
    source: str
    destination: str
    discard: str


@dataclass
class ApiKeysConfig:
    acoustid: Optional[str] = None
    spotify_client_id: Optional[str] = None
    spotify_client_secret: Optional[str] = None
    brave: Optional[str] = None


@dataclass
class LlmConfig:
    base_url: str = "https://api.openai.com/v1"
    api_key: Optional[str] = None
    model: str = "gpt-4o"


@dataclass
class ThresholdsConfig:
    auto_approve: int = 90
    quick_review: int = 70


@dataclass
class NamingConfig:
    file_pattern: str = "{track_number} - {title} - {album} - {album_artist}"
    dir_pattern: str = "{album_artist_initial}/{album_artist}/{album}"


@dataclass
class Config:
    paths: PathsConfig
    api_keys: ApiKeysConfig = field(default_factory=ApiKeysConfig)
    llm: LlmConfig = field(default_factory=LlmConfig)
    thresholds: ThresholdsConfig = field(default_factory=ThresholdsConfig)
    naming: NamingConfig = field(default_factory=NamingConfig)


ENV_VAR_PATTERN = re.compile(r"\$\{(\w+)\}")


def _resolve_env_vars(value: str) -> Optional[str]:
    """Replace ${VAR_NAME} patterns with environment variable values."""
    if not isinstance(value, str):
        return value

    def replace_match(match):
        var_name = match.group(1)
        return os.environ.get(var_name, "")

    resolved = ENV_VAR_PATTERN.sub(replace_match, value)
    return resolved if resolved else None


def _resolve_dict(d: dict) -> dict:
    """Recursively resolve environment variables in a dict."""
    resolved = {}
    for key, value in d.items():
        if isinstance(value, dict):
            resolved[key] = _resolve_dict(value)
        elif isinstance(value, str):
            resolved[key] = _resolve_env_vars(value)
        else:
            resolved[key] = value
    return resolved


def load_config(config_path: str = "config.yaml") -> Config:
    """Load configuration from YAML file with environment variable resolution."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found: {config_path}\n"
            f"Copy config.example.yaml to config.yaml and fill in your settings."
        )

    with open(path) as f:
        raw = yaml.safe_load(f)

    data = _resolve_dict(raw)

    paths = PathsConfig(**data.get("paths", {}))
    api_keys = ApiKeysConfig(**data.get("api_keys", {}))
    llm = LlmConfig(**data.get("llm", {}))
    thresholds = ThresholdsConfig(**data.get("thresholds", {}))
    naming = NamingConfig(**data.get("naming", {}))

    return Config(
        paths=paths,
        api_keys=api_keys,
        llm=llm,
        thresholds=thresholds,
        naming=naming,
    )
