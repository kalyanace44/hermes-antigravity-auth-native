"""
Antigravity model provider profile for Hermes Agent.
Uses ProviderProfile + register_provider — the correct Hermes providers API.
The proxy running on port 8999 exposes /v1/models dynamically, so
fetch_models() picks up the live list automatically.
"""

from providers import register_provider
from providers.base import ProviderProfile


class AntigravityProfile(ProviderProfile):
    """Google Antigravity proxy — static fallback list + live /v1/models catalog."""

    def fetch_models(self, *, api_key=None, base_url=None, timeout=8.0):
        """
        Hit the local proxy's /v1/models endpoint.
        Falls back to the static MODELS list if the proxy is not running.
        """
        result = super().fetch_models(
            api_key=api_key,
            base_url=base_url or self.base_url,
            timeout=timeout,
        )
        return result if result else None


antigravity = AntigravityProfile(
    name="antigravity",
    aliases=("antigravity-auth", "agy", "google-antigravity"),
    display_name="Antigravity",
    description="Google Antigravity models via isolated local proxy (port 8999)",
    base_url="http://127.0.0.1:8999/v1",
    auth_type="api_key",
    env_vars=(),          # no API key needed — proxy handles OAuth internally
    supports_vision=True,
    supports_health_check=True,
)

register_provider(antigravity)
