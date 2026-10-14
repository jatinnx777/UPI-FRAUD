"""Stage 2 - QR decoding.

Reads raw image bytes and returns the text encoded in the QR code.
The decoded payload is treated as untrusted data: it is only returned as a
string, never opened, fetched or executed.
"""

from dataclasses import dataclass

import cv2
import numpy as np

MAX_FILE_BYTES = 4 * 1024 * 1024  # 4 MB (Vercel caps request bodies at 4.5 MB)
ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/jpg"}

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"


class DecodeError(Exception):
    """Raised when the upload cannot be turned into a QR payload."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class DecodeResult:
    payload: str
    width: int
    height: int


def validate_image_bytes(data: bytes, content_type: str | None) -> None:
    if not data:
        raise DecodeError("empty_file", "The uploaded file is empty.")
    if len(data) > MAX_FILE_BYTES:
        raise DecodeError("file_too_large", "The file is larger than the 4 MB limit.")
    if content_type and content_type.lower() not in ALLOWED_CONTENT_TYPES:
        raise DecodeError("unsupported_type", "Only PNG and JPG/JPEG images are supported.")
    # Check the real file signature, not just the declared type or extension.
    if not (data.startswith(PNG_MAGIC) or data.startswith(JPEG_MAGIC)):
        raise DecodeError("unsupported_type", "The file is not a valid PNG or JPEG image.")


def _candidates(img: np.ndarray):
    """Yield progressively processed versions of the image to improve detection."""
    yield img
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    yield gray
    h, w = gray.shape
    if max(h, w) < 1000:  # small screenshots decode better when upscaled
        yield cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    if max(h, w) > 2000:  # very large photos decode better when downscaled
        scale = 1600 / max(h, w)
        yield cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    yield cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    # Add a quiet zone in case the QR touches the image border (tight crops).
    yield cv2.copyMakeBorder(gray, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=255)


def decode_qr(data: bytes, content_type: str | None = None) -> DecodeResult:
    validate_image_bytes(data, content_type)

    img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise DecodeError("unreadable_image", "The image could not be read. It may be corrupted.")

    detector = cv2.QRCodeDetector()
    found_qr = False
    for candidate in _candidates(img):
        text, points, _ = detector.detectAndDecode(candidate)
        if points is not None:
            found_qr = True
        if text:
            return DecodeResult(payload=text, width=img.shape[1], height=img.shape[0])

    if found_qr:
        raise DecodeError(
            "qr_not_decodable",
            "A QR-like pattern was found but could not be decoded. Try a sharper, well-lit image.",
        )
    raise DecodeError("no_qr_found", "No QR code was detected in the image.")
