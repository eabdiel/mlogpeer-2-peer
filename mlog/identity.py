from __future__ import annotations
import hashlib
from typing import Dict
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization
from .util import b64, b64d, atomic_write_json, load_json

def ensure_identity(identity_path: str) -> Dict[str, str]:
    ident = load_json(identity_path, {})
    if ident.get("private_key_b64") and ident.get("public_key_b64") and ident.get("author_id"):
        return ident

    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key()

    priv_bytes = priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_bytes = pub.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    author_id = hashlib.sha256(pub_bytes).hexdigest()[:16]
    ident = {
        "author_id": author_id,
        "public_key_b64": b64(pub_bytes),
        "private_key_b64": b64(priv_bytes),
        "display_name": f"node-{author_id}",
    }
    atomic_write_json(identity_path, ident)
    return ident

def load_private_key(ident: Dict[str, str]) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(b64d(ident["private_key_b64"]))

def load_public_key(pub_b64: str) -> Ed25519PublicKey:
    return Ed25519PublicKey.from_public_bytes(b64d(pub_b64))
