"""
Custom exceptions for better error handling and user feedback
"""


class ImageValidationError(Exception):
    """Base class for image validation errors"""
    pass


class ImageTooLargeError(ImageValidationError):
    """Raised when uploaded image exceeds size limit"""

    def __init__(self, max_size_mb: int):
        self.max_size_mb = max_size_mb
        super().__init__(
            f"Image file is too large. Maximum size allowed is {max_size_mb}MB.")


class UnsupportedImageFormatError(ImageValidationError):
    """Raised when uploaded file is not a valid image format"""

    def __init__(self):
        super().__init__("The uploaded file is not a valid image. Please upload a JPG, PNG, or HEIC image. If you're using an iPhone, try taking a new photo or selecting from your gallery.")


class CorruptedImageError(ImageValidationError):
    """Raised when image file is corrupted or unreadable"""

    def __init__(self):
        super().__init__("The image file appears to be corrupted or damaged. Please try uploading a different image.")
