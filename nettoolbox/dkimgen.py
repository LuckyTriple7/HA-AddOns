"""DKIM key pair generation for the record-generator UI.

A fresh keypair, not a check: nothing here touches the network, so it costs
no quota and leaves no history row -- see app.py's /api/dkim/generate.
cryptography is a hard requirement (requirements.txt), but the import stays
guarded the same way settings.py does it: a broken install must disable this
one button, not crash the whole app.
"""

import base64

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    AVAILABLE = True
except Exception:  # library missing or broken
    AVAILABLE = False

# 2048 bit is current DKIM best practice; 1024 is widely considered too weak
# and some receivers already reject it outright, so there is no reason to
# offer it as a choice.
KEY_SIZE = 2048


def generate() -> dict:
    """A fresh RSA key pair for one selector: the private key as PEM, for the
    mail server's DKIM signer, and the public key as base64, for the p= tag
    of the DNS record. Neither is stored anywhere -- the caller shows the
    private key exactly once and never sends it back."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=KEY_SIZE)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode('ascii')
    public_der = key.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return {'private_key': private_pem,
            'public_key': base64.b64encode(public_der).decode('ascii')}
