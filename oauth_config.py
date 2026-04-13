"""
ButterClaw v0.5.0 — OAuth Provider Registry
=====================================================================
Skeleton configuration for OAuth-capable API providers.
Maps provider names to their OAuth endpoints, scopes, and metadata.

Currently no providers offer public OAuth for API key access,
so this registry is infrastructure-ready for when they do.
The ButterVault stores tokens encrypted at rest using the same
Fernet + keyring architecture as raw API keys.

Usage:
    from oauth_config import OAUTH_PROVIDERS, get_provider, list_providers

    provider = get_provider("anthropic")
    if provider and provider["oauth_supported"]:
        redirect_url = provider["authorize_url"]
        ...

Security:
    - client_secret is NEVER stored here — it lives in the ButterVault
    - state param MUST be validated on callback (CSRF prevention)
    - refresh tokens are encrypted at rest alongside access tokens
    - if the Vault is buttered (panic), all OAuth tokens are destroyed too
"""

# =====================================================================
# PROVIDER REGISTRY
# =====================================================================

OAUTH_PROVIDERS = {
    "anthropic": {
        "display_name": "Anthropic (Claude)",
        "short_code": "AN",
        "oauth_supported": False,  # No public OAuth flow as of April 2026
        "auth_method": "api_key",  # Manual paste into ButterVault
        "authorize_url": None,
        "token_url": None,
        "revoke_url": None,
        "scopes": [],
        "notes": "Anthropic uses static API keys from console.anthropic.com. "
                 "OAuth plumbing is ready — flip oauth_supported when they ship it."
    },
    "openrouter": {
        "display_name": "OpenRouter",
        "short_code": "OR",
        "oauth_supported": False,
        "auth_method": "api_key",
        "authorize_url": None,
        "token_url": None,
        "revoke_url": None,
        "scopes": [],
        "notes": "OpenRouter uses static API keys. Primary provider for ButterClaw."
    },
    "google": {
        "display_name": "Google Cloud (Gemini)",
        "short_code": "GC",
        "oauth_supported": True,  # Google Cloud supports OAuth 2.0
        "auth_method": "oauth2",
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "revoke_url": "https://oauth2.googleapis.com/revoke",
        "scopes": [
            "https://www.googleapis.com/auth/generative-language"
        ],
        "notes": "Google Cloud OAuth is functional. Requires a GCP project with "
                 "Generative Language API enabled. client_id and client_secret "
                 "must be stored in the ButterVault before initiating the flow."
    },
    "github": {
        "display_name": "GitHub",
        "short_code": "GH",
        "oauth_supported": True,
        "auth_method": "oauth2",
        "authorize_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "revoke_url": None,  # GitHub uses DELETE /applications/{client_id}/token
        "scopes": ["repo", "read:user"],
        "notes": "GitHub OAuth is functional. Useful for future integrations "
                 "(e.g., auto-commit audit logs to a private repo)."
    }
}


# =====================================================================
# HELPER FUNCTIONS
# =====================================================================

def get_provider(name):
    """
    Look up a provider by name (case-insensitive).
    Returns the provider dict or None if not found.
    """
    return OAUTH_PROVIDERS.get(name.lower())


def list_providers():
    """Return all registered provider names."""
    return list(OAUTH_PROVIDERS.keys())


def list_oauth_capable():
    """Return names of providers that support OAuth."""
    return [name for name, cfg in OAUTH_PROVIDERS.items() if cfg["oauth_supported"]]


def list_api_key_only():
    """Return names of providers that require manual API key entry."""
    return [name for name, cfg in OAUTH_PROVIDERS.items() if not cfg["oauth_supported"]]


def get_auth_method(name):
    """
    Returns the auth method for a provider: 'oauth2' or 'api_key'.
    Returns None if provider not found.
    """
    provider = get_provider(name)
    return provider["auth_method"] if provider else None
