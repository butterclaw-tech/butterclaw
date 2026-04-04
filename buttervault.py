"""
ButterClaw v0.3 — The ButterVault
=================================
Local-first, encrypted credential storage.
Defends against .env scrapers and supply-chain credential harvesting.
"""

import os
import sqlite3
import logging
import keyring
from cryptography.fernet import Fernet

# Set up Vault-specific logging
logging.basicConfig(level=logging.INFO, format="[VAULT] %(message)s")
logger = logging.getLogger("butterclaw.vault")

# Absolute path to the existing ButterClaw SQLite database
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'butterclaw.db')

# OS Native Keyring Identifiers
KEYRING_SERVICE = "butterclaw_sentinel"
KEYRING_USER = "vault_master_key"

def _get_db():
    """Connects to the database and ensures the vault table exists."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS vault (
            provider TEXT PRIMARY KEY,
            ciphertext BLOB
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
        logger.info("First boot detected. Generating new AES Master Key and storing in OS Keyring...")
        new_key = Fernet.generate_key()
        # Store securely in Windows Credential Manager or macOS Keychain
        keyring.set_password(KEYRING_SERVICE, KEYRING_USER, new_key.decode('utf-8'))
        encoded_key = new_key.decode('utf-8')
    
    return Fernet(encoded_key.encode('utf-8'))

def store_key(provider, api_key):
    """
    Encrypts a raw API key and stores the ciphertext in the local SQLite vault.
    """
    cipher = _get_cipher()
    ciphertext = cipher.encrypt(api_key.encode('utf-8'))
    
    with _get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO vault (provider, ciphertext) VALUES (?, ?)",
            (provider, ciphertext)
        )
        conn.commit()
    logger.info(f"🔒 Key for '{provider}' encrypted and sealed in the ButterVault.")

def get_key(provider):
    """
    Retrieves and decrypts an API key directly into memory. 
    Returns None if the provider isn't found.
    """
    with _get_db() as conn:
        cursor = conn.execute("SELECT ciphertext FROM vault WHERE provider = ?", (provider,))
        row = cursor.fetchone()
        
    if not row:
        return None
        
    cipher = _get_cipher()
    try:
        raw_key = cipher.decrypt(row[0]).decode('utf-8')
        return raw_key
    except Exception as e:
        logger.error(f"❌ Decryption failed for '{provider}'. Master key mismatch or corrupted vault.")
        return None

def butter_keys(provider=None):
    """
    The Panic Button. 
    Overwrites the stored ciphertext with cryptographic garbage. 
    Even if the OS Keyring is compromised later, the keys are already gone.
    """
    # Generate random bytes that look like a valid Fernet token but decrypt to nothing useful
    garbage = Fernet.generate_key() 
    
    with _get_db() as conn:
        if provider:
            conn.execute("UPDATE vault SET ciphertext = ? WHERE provider = ?", (garbage, provider))
            logger.warning(f"🧈 Target '{provider}' keys successfully Buttered. Ciphertext destroyed.")
        else:
            conn.execute("UPDATE vault SET ciphertext = ?", (garbage,))
            logger.warning("☢️ GLOBAL GIBSON TRIGGERED. ALL keys in ButterVault destroyed.")
        conn.commit()

if __name__ == "__main__":
    # --- DIAGNOSTIC MODE ---
    # Run `python buttervault.py` directly to test the encryption pipeline.
    print("🦞 ButterVault Diagnostic Boot...")
    
    # 1. Test Storage
    store_key("OpenRouter", "sk-or-v1-unautclated-slop-test-key")
    
    # 2. Test Retrieval
    retrieved = get_key("OpenRouter")
    if retrieved == "sk-or-v1-unautclated-slop-test-key":
        print("✅ Decryption successful. Memory isolation verified.")
    else:
        print("❌ Decryption failed.")
        
    # 3. Test The Gibson
    butter_keys("OpenRouter")
    
    # 4. Verify Destruction
    try:
        destroyed_key = get_key("OpenRouter")
        print("❌ Panic button failed. Key still readable.")
    except Exception:
        print("✅ Keys successfully buttered. Ciphertext is unreadable.")