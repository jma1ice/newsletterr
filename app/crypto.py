import os, secrets
from cryptography.fernet import Fernet, InvalidToken
from dotenv import set_key

from app import config

def ensure_data_key() -> str:
    key = os.getenv("DATA_ENC_KEY")
    if key:
        return key

    new_key = Fernet.generate_key().decode()
    set_key(str(config.ENV_FILE), "DATA_ENC_KEY", new_key)
    return new_key

def ensure_secret_key() -> str:
    # Flask session-signing key, persisted so restarts don't log everyone
    # out or rotate CSRF tokens mid-flight (same pattern as ensure_data_key).
    key = os.getenv("NEWSLETTERR_SECRET_KEY")
    if key:
        return key

    new_key = secrets.token_hex(32)
    set_key(str(config.ENV_FILE), "NEWSLETTERR_SECRET_KEY", new_key)
    # set_key writes the file but not the process env; cache it so repeated
    # create_app() calls in one process can't regenerate a different key
    os.environ["NEWSLETTERR_SECRET_KEY"] = new_key
    return new_key

DATA_KEY = ensure_data_key()
fernet = Fernet(DATA_KEY)

def encrypt(token: str) -> str:
    return fernet.encrypt(token.encode()).decode()

def decrypt(encrypted: str) -> str:
    if encrypted is None:
        return ""
    try:
        return fernet.decrypt(encrypted.encode()).decode()
    except InvalidToken:
        return encrypted
