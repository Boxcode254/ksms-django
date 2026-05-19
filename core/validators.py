import magic
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator, RegexValidator
from django.utils.translation import gettext_lazy as _

MIME_TYPE_MAP = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

MAX_UPLOAD_SIZE = 5 * 1024 * 1024

kenya_phone_validator = RegexValidator(
    regex=r"^(?:\+254|254|0)(?:7\d{8}|1\d{8})$",
    message=_(
        "Enter a valid Kenyan phone number in the format 07XXXXXXXX, 01XXXXXXXX, 2547XXXXXXXX, or +2547XXXXXXXX."
    ),
)

mpesa_code_validator = RegexValidator(
    regex=r"^[A-Z0-9]{8,15}$",
    message=_("Enter a valid M-Pesa transaction or receipt code."),
)

positive_money_validator = MinValueValidator(Decimal("0.01"))
non_negative_money_validator = MinValueValidator(Decimal("0.00"))
percentage_min_validator = MinValueValidator(Decimal("0.00"))
percentage_max_validator = MaxValueValidator(Decimal("100.00"))


class FileTypeValidator:
    def __init__(self, allowed_extensions=None, allowed_mime_types=None):
        self.allowed_extensions = allowed_extensions or []
        self.allowed_mime_types = allowed_mime_types or set()

    def __call__(self, value):
        ext = value.name.rsplit(".", 1)[-1].lower() if "." in value.name else ""
        if self.allowed_extensions and ext not in self.allowed_extensions:
            raise ValidationError(
                _("File type '%(ext)s' is not allowed. Allowed types: %(allowed)s."),
                params={"ext": ext, "allowed": ", ".join(self.allowed_extensions)},
            )

        if self.allowed_mime_types:
            try:
                file_mime = magic.from_buffer(value.read(2048), mime=True)
                value.seek(0)
            except Exception:
                value.seek(0)
                return

            if file_mime not in self.allowed_mime_types:
                expected = MIME_TYPE_MAP.get(ext)
                if expected and file_mime != expected:
                    raise ValidationError(
                        _("File content does not match the expected type for '%(ext)s' files."),
                        params={"ext": ext},
                    )

    def __eq__(self, other):
        return (
            isinstance(other, FileTypeValidator)
            and self.allowed_extensions == other.allowed_extensions
            and self.allowed_mime_types == other.allowed_mime_types
        )

    def deconstruct(self):
        return (
            "core.validators.FileTypeValidator",
            [],
            {
                "allowed_extensions": self.allowed_extensions,
                "allowed_mime_types": self.allowed_mime_types,
            },
        )


class MaxFileSizeValidator:
    def __init__(self, max_size_bytes):
        self.max_size_bytes = max_size_bytes

    def __call__(self, value):
        if value.size > self.max_size_bytes:
            raise ValidationError(
                _("File size must not exceed %(size)s."),
                params={"size": f"{self.max_size_bytes / (1024 * 1024):.0f}MB"},
            )

    def __eq__(self, other):
        return isinstance(other, MaxFileSizeValidator) and self.max_size_bytes == other.max_size_bytes

    def deconstruct(self):
        return ("core.validators.MaxFileSizeValidator", [self.max_size_bytes], {})


def scan_for_malware(file_obj):
    """Placeholder for virus scanning integration.

    Integrate with ClamAV or a cloud scanning service here.
    Example ClamAV integration::

        import clamd
        cd = clamd.ClamdUnixSocket()
        file_obj.seek(0)
        result = cd.instream(file_obj)
        if result['stream'][0] != 'OK':
            raise ValidationError(_('File failed virus scan.'))
    """
    pass


image_upload_validators = [
    FileExtensionValidator(allowed_extensions=["jpg", "jpeg", "png", "webp"]),
    FileTypeValidator(
        allowed_extensions=["jpg", "jpeg", "png", "webp"],
        allowed_mime_types={"image/jpeg", "image/png", "image/webp"},
    ),
    MaxFileSizeValidator(2 * 1024 * 1024),
]

document_upload_validators = [
    FileExtensionValidator(allowed_extensions=["pdf", "jpg", "jpeg", "png", "doc", "docx"]),
    FileTypeValidator(
        allowed_extensions=["pdf", "jpg", "jpeg", "png", "doc", "docx"],
        allowed_mime_types=ALLOWED_MIME_TYPES,
    ),
    MaxFileSizeValidator(MAX_UPLOAD_SIZE),
]

max_image_size_2mb = MaxFileSizeValidator(2 * 1024 * 1024)
