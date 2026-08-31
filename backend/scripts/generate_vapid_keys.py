"""
NEXUS — generates a VAPID key pair in the exact format this backend
expects (base64url-encoded raw key material, NOT PEM).

Run once, from backend/:
    python3 scripts/generate_vapid_keys.py
"""
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def main() -> None:
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()

    private_raw = private_key.private_numbers().private_value.to_bytes(32, "big")
    private_b64 = base64.urlsafe_b64encode(private_raw).decode().rstrip("=")

    public_raw = public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    public_b64 = base64.urlsafe_b64encode(public_raw).decode().rstrip("=")

    print("Add these to your backend's .env (or Render env vars):\n")
    print(f"VAPID_PRIVATE_KEY={private_b64}")
    print(f"VAPID_PUBLIC_KEY={public_b64}")
    print(f"VAPID_SUBJECT=mailto:you@example.com  # replace with a real contact")
    print(
        "\nThe public key also needs to go into the frontend's service-worker "
        "registration code (frontend/src/utils/push.js) — see PUSH_NOTIFICATIONS.md."
    )


if __name__ == "__main__":
    main()
