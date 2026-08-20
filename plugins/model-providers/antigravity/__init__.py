"""
Model provider registration for Hermes Antigravity plugin.
Registers 'antigravity' as a provider pointing to the local proxy on port 8999.
"""

PROVIDER_NAME = "antigravity"
BASE_URL = "http://127.0.0.1:8999/v1"
API_KEY = "mock"

MODELS = [
    "gemini-3.6-flash",
    "gemini-3.6-flash-low",
    "gemini-3.6-flash-high",
    "gemini-3.7-flash",
    "claude-sonnet-4-6",
    "claude-opus-4-6",
    "gpt-oss-120b",
    "gemini-3.1-pro",
    "gemini-3-flash",
    "gemini-2.5-flash",
]


def register(ctx):
    ctx.register_provider(
        name=PROVIDER_NAME,
        base_url=BASE_URL,
        api_key=API_KEY,
        models=MODELS,
        display_name="Antigravity",
        description="Google Antigravity models via isolated local proxy"
    )
