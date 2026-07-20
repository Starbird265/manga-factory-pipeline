import os
import json
import hmac
import hashlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class SecurityManager:
    """
    Handles cryptographic signing and verification of pipeline state files
    to prevent tampering and ensure the pipeline learns from valid data.
    """
    def __init__(self, data_dir: str = '.'):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.key_path = self.data_dir / '.secret_key'
        self._secret_key = self._load_or_generate_key()

    def _load_or_generate_key(self) -> bytes:
        if self.key_path.exists():
            try:
                with open(self.key_path, 'rb') as f:
                    return f.read()
            except Exception as e:
                logger.error(f"Failed to read secret key: {e}")

        # Generate a new 32-byte secret key
        new_key = os.urandom(32)
        try:
            with open(self.key_path, 'wb') as f:
                f.write(new_key)
            # Secure the key file permissions on unix systems
            try:
                os.chmod(self.key_path, 0o600)
            except Exception:
                pass
            logger.info("Generated new security key for pipeline cache.")
        except Exception as e:
            logger.error(f"Failed to write secret key: {e}")

        return new_key

    def sign_data(self, data: dict) -> dict:
        """
        Takes a dictionary, serializes it (ignoring existing signature),
        computes an HMAC-SHA256 signature, and injects it.
        """
        # Create a copy without the signature to compute the hash
        clean_data = {k: v for k, v in data.items() if k != '_signature'}
        serialized = json.dumps(clean_data, sort_keys=True).encode('utf-8')

        signature = hmac.new(self._secret_key, serialized, hashlib.sha256).hexdigest()

        # Return a new dict with the signature
        signed_data = clean_data.copy()
        signed_data['_signature'] = signature
        return signed_data

    def verify_data(self, data: dict) -> bool:
        """
        Verifies that the dictionary's _signature matches its content.
        If no signature exists, or it fails to match, returns False.
        """
        if '_signature' not in data:
            return False

        provided_signature = data['_signature']
        clean_data = {k: v for k, v in data.items() if k != '_signature'}
        serialized = json.dumps(clean_data, sort_keys=True).encode('utf-8')

        expected_signature = hmac.new(self._secret_key, serialized, hashlib.sha256).hexdigest()

        return hmac.compare_digest(provided_signature, expected_signature)
