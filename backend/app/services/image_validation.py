"""
app/services/image_validation.py
──────────────────────────────────
Profile picture upload validation and processing.
Validates file type, size, and dimensions before storage.
"""

import io
from typing import BinaryIO

from PIL import Image

from app.core.logging import get_logger

logger = get_logger(__name__)

# Image constraints
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
MIN_WIDTH = 500
MIN_HEIGHT = 500
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}


class ImageValidationError(Exception):
    """Raised when image validation fails."""
    pass


def validate_image_file(
    file_content: bytes,
    filename: str,
    content_type: str | None = None,
) -> dict[str, int | str]:
    """
    Validates a profile picture file for size, type, and dimensions.
    
    Args:
        file_content: Raw file bytes
        filename: Original filename
        content_type: MIME type from Content-Type header
    
    Returns:
        Dictionary with 'width', 'height', 'extension', and 'format'
    
    Raises:
        ImageValidationError: If validation fails
    """
    # 1. Check file size
    file_size = len(file_content)
    if file_size == 0:
        raise ImageValidationError("File is empty.")
    if file_size > MAX_FILE_SIZE_BYTES:
        raise ImageValidationError(
            f"File is too large. Maximum size is 5 MB, but received {file_size / (1024*1024):.1f} MB."
        )

    # 2. Check file extension
    filename_lower = filename.lower()
    file_ext = None
    for ext in ALLOWED_EXTENSIONS:
        if filename_lower.endswith(ext):
            file_ext = ext.lstrip(".")
            break
    
    if not file_ext:
        raise ImageValidationError(
            f"Invalid file type. Allowed types are: JPG, PNG. Received: {filename}"
        )

    # 3. Check MIME type if provided
    if content_type:
        mime_lower = content_type.lower().strip()
        if mime_lower not in ALLOWED_MIME_TYPES:
            raise ImageValidationError(
                f"Invalid MIME type '{content_type}'. Allowed types are: image/jpeg, image/png."
            )

    # 4. Validate image dimensions
    try:
        img = Image.open(io.BytesIO(file_content))
        img.load()  # Force load to ensure validity
        
        width, height = img.size
        
        if width < MIN_WIDTH or height < MIN_HEIGHT:
            raise ImageValidationError(
                f"Image too small. Minimum dimensions are {MIN_WIDTH}x{MIN_HEIGHT}px, "
                f"but received {width}x{height}px."
            )
        
        # Get actual format
        fmt = img.format or "JPEG"
        
        return {
            "width": width,
            "height": height,
            "extension": file_ext,
            "format": fmt,
        }
    
    except ImageValidationError:
        raise
    except Exception as exc:
        logger.error(
            "Image validation failed: could not open or read image",
            filename=filename,
            error=str(exc),
        )
        raise ImageValidationError(
            "Could not read the image file. Please ensure it's a valid JPG or PNG."
        )


def get_file_extension_from_upload(
    filename: str,
) -> str:
    """
    Extracts the file extension from an uploaded filename.
    Returns lowercase extension without the dot (e.g., 'jpg', 'png').
    """
    filename_lower = filename.lower()
    for ext in ALLOWED_EXTENSIONS:
        if filename_lower.endswith(ext):
            return ext.lstrip(".")
    return "jpg"  # Default fallback
