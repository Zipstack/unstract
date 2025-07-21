"""Custom Django model fields and serializer fields for common use cases."""

import json
import logging
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models
from rest_framework import serializers

from utils.exceptions import InvalidEncryptionKey

logger = logging.getLogger(__name__)


class EncryptedBinaryField(models.BinaryField):
    """A BinaryField that automatically encrypts/decrypts JSON data.

    This field transparently handles encryption when storing data to the database
    and decryption when retrieving data from the database. It expects dictionary
    data as input and returns dictionary data as output.

    Features:
    - Automatic encryption/decryption using Fernet symmetric encryption
    - JSON serialization/deserialization
    - Proper error handling for encryption failures
    - Null value support
    - Compatible with Django ORM and DRF serializers

    Usage:
        class MyModel(models.Model):
            encrypted_data = EncryptedBinaryField(null=True)

        # Usage is transparent
        instance = MyModel.objects.create(encrypted_data={'key': 'value'})
        print(instance.encrypted_data)  # {'key': 'value'}
    """

    description = "A binary field that automatically encrypts/decrypts JSON data"

    def __init__(self, *args, **kwargs):
        # Remove any JSON-specific kwargs that might be passed
        kwargs.pop("encoder", None)
        kwargs.pop("decoder", None)
        super().__init__(*args, **kwargs)

    def _get_encryption_key(self) -> bytes:
        """Get the encryption key from Django settings."""
        encryption_key = getattr(settings, "ENCRYPTION_KEY", None)
        if not encryption_key:
            raise ValueError("ENCRYPTION_KEY not found in Django settings")
        return encryption_key.encode("utf-8")

    def _encrypt_value(self, value: Any) -> bytes:
        """Encrypt a Python value (typically dict) to bytes."""
        if value is None:
            return None

        try:
            # Serialize to JSON string
            json_string = json.dumps(value)

            # Encrypt the JSON string
            cipher_suite = Fernet(self._get_encryption_key())
            encrypted_bytes = cipher_suite.encrypt(json_string.encode("utf-8"))

            return encrypted_bytes
        except Exception as e:
            logger.error(f"Failed to encrypt value: {e}")
            raise

    def _decrypt_value(self, value: bytes) -> dict | None:
        """Decrypt bytes to a Python value (typically dict)."""
        if value is None:
            return None

        try:
            # Handle memoryview objects from database
            if isinstance(value, memoryview):
                value = value.tobytes()

            # If it's already a dict, return as-is (for backward compatibility)
            if isinstance(value, dict):
                return value

            # Decrypt the bytes
            cipher_suite = Fernet(self._get_encryption_key())
            decrypted_bytes = cipher_suite.decrypt(value)

            # Parse JSON string back to Python object
            json_string = decrypted_bytes.decode("utf-8")
            return json.loads(json_string)

        except InvalidToken:
            logger.error("Invalid encryption token - possibly wrong encryption key")
            raise InvalidEncryptionKey(entity=InvalidEncryptionKey.Entity.CONNECTOR)
        except Exception as e:
            logger.error(f"Failed to decrypt value: {e}")
            raise

    def from_db_value(self, value, expression, connection):
        """Convert database value to Python value.
        Called when data is loaded from the database.
        """
        return self._decrypt_value(value)

    def to_python(self, value):
        """Convert input value to Python value.
        Called during model validation and form processing.
        """
        if value is None:
            return value

        # If it's already a Python object (dict), return as-is
        if isinstance(value, dict):
            return value

        # If it's bytes (encrypted), decrypt it
        if isinstance(value, (bytes, memoryview)):
            return self._decrypt_value(value)

        # If it's a string, try to parse as JSON
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                pass

        return value

    def get_prep_value(self, value):
        """Convert Python value to database value.
        Called before saving to the database.
        """
        if value is None:
            return None

        # If it's already bytes (encrypted), return as-is
        if isinstance(value, (bytes, memoryview)):
            return value

        # Encrypt the value
        return self._encrypt_value(value)

    def get_db_prep_value(self, value, connection, prepared=False):
        """Convert Python value to database-specific value."""
        if not prepared:
            value = self.get_prep_value(value)
        return super().get_db_prep_value(value, connection, prepared)

    def value_to_string(self, obj):
        """Convert field value to string for serialization."""
        value = self.value_from_object(obj)
        if value is None:
            return None
        return json.dumps(value)

    def formfield(self, **kwargs):
        """Return a form field for this model field."""
        # Use a CharField for forms since we want JSON input
        from django import forms

        defaults = {"widget": forms.Textarea}
        defaults.update(kwargs)
        return forms.CharField(**defaults)


class EncryptedBinaryFieldSerializer(serializers.Field):
    """Custom serializer field for EncryptedBinaryField.

    This field handles serialization/deserialization of encrypted binary data
    as JSON dictionaries, making it compatible with DRF's serialization process.
    """

    def to_representation(self, value):
        """Convert encrypted binary data to JSON dictionary for API responses."""
        if value is None:
            return None

        # The EncryptedBinaryField already decrypts the value when accessed
        # so we just need to return it as-is
        return value

    def to_internal_value(self, data):
        """Convert JSON dictionary to internal value for database storage."""
        if data is None:
            return None

        # Validate that the data is a dictionary
        if not isinstance(data, dict):
            raise serializers.ValidationError("Expected a dictionary.")

        # Return the data as-is; the EncryptedBinaryField will handle encryption
        return data
