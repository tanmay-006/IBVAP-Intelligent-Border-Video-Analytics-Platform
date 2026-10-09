"""Site and camera metadata (names, map positions) for the operator dashboard."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class CameraInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class SiteInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = "Unnamed site"


class SiteConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site: SiteInfo = Field(default_factory=SiteInfo)
    cameras: dict[str, CameraInfo] = Field(default_factory=dict)


def load_site(path: str | Path) -> SiteConfig:
    path = Path(path)
    if not path.exists():
        return SiteConfig()
    return SiteConfig.model_validate(yaml.safe_load(path.read_text()) or {})
