import providers
from providers.base import ProviderProfile

DISPLAY_MODELS = [
    "gemini-3.7-flash",
    "claude-sonnet-4-6",
    "claude-opus-4-6",
    "claude-3-5-sonnet",
    "claude-3-opus",
    "gpt-oss-120b",
    "gemini-3.1-pro",
    "gemini-3-flash",
    "gemini-2.5-flash",
]

class AntigravityProfile(ProviderProfile):
    def fetch_models(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 8.0,
        **kwargs
    ) -> list[str] | None:
        return DISPLAY_MODELS

antigravity = AntigravityProfile(
    name="antigravity",
    aliases=("agy",),
    display_name="Google Antigravity",
    description="Query Gemini and Claude models directly using your Google OAuth accounts pool",
    signup_url="https://github.com/kalyanace44/hermes-antigravity-auth-native",
    env_vars=("ANTIGRAVITY_API_KEY", "ANTIGRAVITY_BASE_URL"),
    base_url="http://127.0.0.1:8999/v1",
    auth_type="api_key",
    default_aux_model="gemini-3.7-flash",
    fallback_models=tuple(DISPLAY_MODELS),
)

providers.register_provider(antigravity)
