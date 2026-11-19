import os
from cryptography.fernet import Fernet

def get_cipher(key: str = None) -> Fernet:
    master_key = key or os.environ.get("VIDEO_VAULT_KEY")
    if not master_key:
        raise ValueError("Missing VIDEO_VAULT_KEY environment variable.")
    if isinstance(master_key, str):
        master_key = master_key.encode("utf-8")
    return Fernet(master_key)

def encrypt_bytes(data: bytes, key: str = None) -> bytes:
    return get_cipher(key).encrypt(data)

def decrypt_bytes(data: bytes, key: str = None) -> bytes:
    return get_cipher(key).decrypt(data)

def encrypt_text(text: str, key: str = None) -> str:
    return encrypt_bytes(text.encode("utf-8"), key).decode("utf-8")

def decrypt_text(cipher_text: str, key: str = None) -> str:
    return decrypt_bytes(cipher_text.encode("utf-8"), key).decode("utf-8")
