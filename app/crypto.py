import os
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
