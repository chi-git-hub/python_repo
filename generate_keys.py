from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

# Private key: unencrypted PKCS8 PEM (same as rsa_key.p8 from the openssl command)
private_pem = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)
with open("rsa_key.p8", "wb") as f:
    f.write(private_pem)

# Public key: PEM file plus the single-line body Snowflake needs
public_pem = private_key.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
)
with open("rsa_key.pub", "wb") as f:
    f.write(public_pem)

body = "".join(public_pem.decode().strip().splitlines()[1:-1])
print("Run this in Snowsight (replace CHAITANYA):\n")
print(f"ALTER USER CHAITANYA SET RSA_PUBLIC_KEY='{body}';")