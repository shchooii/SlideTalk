from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv
import streamlit as st

load_dotenv()


def _get_secret(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name)
        if value is not None:
            return str(value)
    except Exception:
        pass
    return os.getenv(name, default)


@dataclass(frozen=True)
class Settings:
    base_url: str = _get_secret(
        "KANANA_BASE_URL",
        "https://kanana-o.a2s-endpoint.kr-central-2.kakaocloud.com/v1",
    )
    model: str = _get_secret("KANANA_MODEL", "kanana-o")
    api_key: str = _get_secret("KANANA_API_KEY", "")

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key.strip())


settings = Settings()
