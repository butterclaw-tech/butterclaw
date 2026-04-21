"""
ButterClaw v0.6.0 — The ButterVault
=================================================
Local-first, encrypted credential storage.
Defends against .env scrapers and supply-chain credential harvesting.
Supports complex OAuth 2.0 token dictionary payloads.
[v0.6.0] The Gibson now hooks into auth.py to destroy API key hashes.
"""

import os
import sqlite3
import logging
import keyring
from cryptography.fernet import Fernet
import json
import time
import datetime

# Set up Vault-specific logging
logger = logging.getLogger("butterclaw.vault")

# Absolute path to the existing ButterClaw SQLite database
#DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'butterclaw.db')

# FIND:
#BASE_DIR = os.path.dirname(os.path.abspath(__file__))
#DB_PATH = os.path.join(BASE_DIR, 'butterclaw.db')

# REPLACE WITH:
#try:
#    from config import cfg
#    DB_PATH = cfg.DB_PATH
#except ImportError:
#    DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'butterclaw.db')

# Keep this line so the diagnostic tests still know where they are!
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

try:
    from config import cfg
    DB_PATH = cfg.DB_PATH
except ImportError:
    DB_PATH = os.path.join(BASE_DIR, 'butterclaw.db')

# OS Native Keyring Identifiers
KEYRING_SERVICE = "butterclaw_sentinel"
KEYRING_USER = "vault_master_key"

def _get_db():
    """Connects to the database and ensures both vault tables exist."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    # Legacy flat-string API keys
    conn.execute('''
        CREATE TABLE IF NOT EXISTS vault (
            provider TEXT PRIMARY KEY,
            ciphertext BLOB
        )
    ''')
    # v0.5.2 OAuth token dictionaries
    conn.execute('''
        CREATE TABLE IF NOT EXISTS oauth_tokens (
            provider    TEXT PRIMARY KEY,
            ciphertext  BLOB NOT NULL,
            created_at  TEXT NOT NULL,
            last_refresh TEXT
        )
    ''')
    return conn

def _get_cipher():
    """
    Retrieves the master AES encryption key from the OS native credential locker.
    If it doesn't exist (first boot), it generates one and locks it away.
    """
    encoded_key = keyring.get_password(KEYRING_SERVICE, KEYRING_USER)
    
    if not encoded_key:
        logger.info("First boot detected. Generating Master Vault Key and sealing in OS Keyring...")
        new_key = Fernet.generate_key()
        keyring.set_password(KEYRING_SERVICE, KEYRING_USER, new_key.decode('utf-8'))
        return Fernet(new_key)
        
    return Fernet(encoded_key.encode('utf-8'))

# =====================================================================
# STATIC API KEY MANAGEMENT (Legacy / Non-OAuth Providers)
# =====================================================================

def store_key(provider, api_key):
    """Encrypts a plaintext string and stores it in the SQLite vault."""
    cipher = _get_cipher()
    ciphertext = cipher.encrypt(api_key.encode('utf-8'))
    
    with _get_db() as conn:
        conn.execute("INSERT OR REPLACE INTO vault (provider, ciphertext) VALUES (?, ?)", 
                     (provider, ciphertext))
        conn.commit()
    logger.info(f"🔐 Key for '{provider}' encrypted and sealed in the ButterVault.")

def get_key(provider):
    """Retrieves and decrypts an API key. Returns None if missing/destroyed."""
    with _get_db() as conn:
        cursor = conn.execute("SELECT ciphertext FROM vault WHERE provider = ?", (provider,))
        row = cursor.fetchone()
        
    if not row:
        return None
        
    cipher = _get_cipher()
    try:
        decrypted = cipher.decrypt(row[0]).decode('utf-8')
        return decrypted
    except Exception as e:
        logger.error(f"❌ Decryption failed for '{provider}'. Key may have been Buttered.")
        return None

def delete_key(provider):
    with _get_db() as conn:
        conn.execute("DELETE FROM vault WHERE provider = ?", (provider,))
        conn.commit()
    logger.info(f"🗑️ Key for '{provider}' removed from ButterVault.")

def list_providers():
    """Returns a list of all providers with stored static keys."""
    with _get_db() as conn:
        cursor = conn.execute("SELECT provider FROM vault ORDER BY provider")
        return [row[0] for row in cursor.fetchall()]

# =====================================================================
# OAUTH TOKEN MANAGEMENT (v0.5.2)
# =====================================================================

def store_oauth_token(provider, token_dict):
    """
    Encrypts an OAuth token dictionary and stores it in the oauth_tokens table.
    """
    if not isinstance(token_dict, dict):
        raise ValueError("token_dict must be a dictionary")
    if "access_token" not in token_dict:
        raise ValueError("token_dict must contain 'access_token'")
    
    # Serialize to JSON, encrypt with the exact same Fernet pipeline
    plaintext = json.dumps(token_dict)
    cipher = _get_cipher()
    ciphertext = cipher.encrypt(plaintext.encode('utf-8'))
    
    now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    
    with _get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO oauth_tokens (provider, ciphertext, created_at, last_refresh) VALUES (?, ?, ?, ?)",
            (provider, ciphertext, now, None)
        )
        conn.commit()
    
    logger.info(f"🔐 OAuth token for '{provider}' encrypted and sealed in the ButterVault.")

def get_oauth_token(provider):
    """
    Retrieves and decrypts an OAuth token dictionary.
    Returns the dict or None if not found/corrupted.
    """
    with _get_db() as conn:
        cursor = conn.execute("SELECT ciphertext FROM oauth_tokens WHERE provider = ?", (provider,))
        row = cursor.fetchone()
    
    if not row:
        return None
    
    cipher = _get_cipher()
    try:
        decrypted = cipher.decrypt(row[0]).decode('utf-8')
        return json.loads(decrypted)
    except Exception as e:
        logger.error(f"❌ OAuth token decryption failed for '{provider}'. Vault may be corrupted or Buttered.")
        return None

def delete_oauth_token(provider):
    """Remove a single OAuth token from the vault."""
    with _get_db() as conn:
        conn.execute("DELETE FROM oauth_tokens WHERE provider = ?", (provider,))
        conn.commit()
    logger.info(f"🗑️ OAuth token for '{provider}' removed from ButterVault.")

def list_oauth_providers():
    """Returns a list of all providers with stored OAuth tokens."""
    with _get_db() as conn:
        cursor = conn.execute("SELECT provider FROM oauth_tokens ORDER BY provider")
        return [row[0] for row in cursor.fetchall()]

def refresh_token_if_needed(provider, token_url, client_id, client_secret=None):
    """
    Check if the stored OAuth token is expired. If so, use the refresh_token
    to silently obtain a new access_token, re-encrypt, and update the Vault.
    """
    import requests as http_req
    
    token_dict = get_oauth_token(provider)
    if token_dict is None:
        return None
    
    expires_at = token_dict.get("expires_at", 0)
    
    # Add 60s buffer — refresh before actual expiry to prevent race conditions
    if time.time() < (expires_at - 60):
        return token_dict  # Still valid
    
    refresh_token = token_dict.get("refresh_token")
    if not refresh_token:
        logger.warning(f"⚠️ OAuth token for '{provider}' expired and no refresh_token available.")
        return None
    
    logger.info(f"🔄 OAuth token for '{provider}' expired. Refreshing...")
    
    try:
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id
        }
        if client_secret:
            payload["client_secret"] = client_secret

        resp = http_req.post(token_url, data=payload, timeout=15)
        
        if resp.status_code != 200:
            logger.error(f"❌ Token refresh failed for '{provider}': HTTP {resp.status_code}")
            return None
        
        new_tokens = resp.json()
        
        # Update the stored token dict
        token_dict["access_token"] = new_tokens["access_token"]
        token_dict["expires_at"] = time.time() + new_tokens.get("expires_in", 3600)
        token_dict["token_type"] = new_tokens.get("token_type", "Bearer")
        
        # Some providers rotate refresh tokens — update if a new one is issued
        if "refresh_token" in new_tokens:
            token_dict["refresh_token"] = new_tokens["refresh_token"]
        
        # Re-encrypt and store
        store_oauth_token(provider, token_dict)
        
        now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        with _get_db() as conn:
            conn.execute(
                "UPDATE oauth_tokens SET last_refresh = ? WHERE provider = ?",
                (now, provider)
            )
            conn.commit()
        
        logger.info(f"✅ OAuth token for '{provider}' refreshed successfully.")
        return token_dict
        
    except Exception as e:
        logger.error(f"❌ Token refresh request failed for '{provider}': {e}")
        return None

# =====================================================================
# THE GIBSON (Kinetic Failsafe)
# =====================================================================

def butter_keys(provider=None):
    """
    The Panic Button. Overwrites ALL stored ciphertext with cryptographic garbage.
    Destroys both static API keys AND OAuth token dictionaries.
    """
    # Generating a random Fernet key ensures decryption will never be successful
    garbage = Fernet.generate_key() 
    
    with _get_db() as conn:
        if provider:
            conn.execute("UPDATE vault SET ciphertext = ? WHERE provider = ?", (garbage, provider))
            conn.execute("UPDATE oauth_tokens SET ciphertext = ? WHERE provider = ?", (garbage, provider))
            logger.warning(f"🧈 Target '{provider}' keys + OAuth tokens successfully Buttered.")
        else:
            conn.execute("UPDATE vault SET ciphertext = ?", (garbage,))
            conn.execute("UPDATE oauth_tokens SET ciphertext = ?", (garbage,))
            logger.warning("☢️ GLOBAL GIBSON TRIGGERED. ALL keys AND OAuth tokens destroyed.")
        conn.commit()

    # [v0.6.0] Destroy API key hashes — invalidates all auth
    try:
        import auth
        auth.destroy_all_api_keys()
    except ImportError:
        pass  # auth module not present (pre-v0.6.0 compat)

if __name__ == "__main__":
    # --- DIAGNOSTIC MODE ---
    print("🦞 ButterVault Diagnostic Boot...")
    
    # 1. Test Static Storage
    store_key("OpenRouter", "sk-or-v1-unautclated-slop-test-key")
    retrieved = get_key("OpenRouter")
    if retrieved == "sk-or-v1-unautclated-slop-test-key":
        print("✅ Static decryption successful.")
    else:
        print("❌ Static decryption failed.")
        
    # 2. Test OAuth Storage
    test_token = {
        "access_token": "ya29.test-oauth-token",
        "refresh_token": "1//test-refresh-token",
        "expires_at": time.time() + 3600,
        "token_type": "Bearer",
        "scope": "https://www.googleapis.com/auth/generative-language"
    }
    store_oauth_token("google_test", test_token)
    retrieved_oauth = get_oauth_token("google_test")
    if retrieved_oauth and retrieved_oauth["access_token"] == "ya29.test-oauth-token":
        print("✅ OAuth token encryption/decryption successful.")
    else:
        print("❌ OAuth token test failed.")
        
    # 3. Test The Gibson (Destroys Both)
    butter_keys()
    
    # 4. Verify Destruction
    if get_key("OpenRouter") is None and get_oauth_token("google_test") is None:
        print("✅ GLOBAL GIBSON SUCCESSFUL. All auth payloads mathematically annihilated.")
    else:
        print("❌ PANIC BUTTON FAILED. Data still readable.")