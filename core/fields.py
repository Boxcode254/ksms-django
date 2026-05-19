from django.db import models

from .encryption import decrypt_value, encrypt_value


class EncryptedTextField(models.TextField):
    description = "Encrypted text field"

    def from_db_value(self, value, expression, connection):
        return decrypt_value(value)

    def to_python(self, value):
        value = super().to_python(value)
        # Only decrypt if the value looks like an encrypted Fernet token.
        # This prevents double-decryption when to_python is called after
        # from_db_value has already decrypted the value.
        if isinstance(value, str) and value.startswith("gAAAA"):
            return decrypt_value(value)
        return value

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        return encrypt_value(value)
