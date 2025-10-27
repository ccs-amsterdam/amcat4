import hashlib
import io
import base64
import requests
from PIL import Image
from typing import Optional

from amcat4.models import ImageObject


def create_image_from_url(url: str) -> ImageObject | None:
    base64 = compress_image_from_url_to_base64(url)
    if base64 is None:
        return None

    hash = hashlib.sha256(base64.encode("utf-8")).hexdigest() if base64 else ""
    return ImageObject(hash=hash, base64=base64)


def compress_image_from_url_to_base64(url: str, max_kb: int = 100, format: str = "JPEG") -> Optional[str]:
    """
    Loads an image from a URL, compresses it, and returns the Base64 string.
    """
    # 1. Load the image
    img = _load_image_from_url(url)
    if img is None:
        return None

    max_bytes = max_kb * 1024

    # 2. Compress the image iteratively
    compressed_data = _iterative_compress(img, max_bytes, format)
    if compressed_data is None:
        return None

    # 3. Encode the compressed binary data to Base64
    return _encode_to_base64(compressed_data)


def compress_image_from_bytes_to_base64(image_data: bytes, max_kb: int = 100, format: str = "JPEG") -> Optional[str]:
    """
    Loads an image from binary data, compresses it, and returns the Base64 string.
    """
    # 1. Load the image
    img = _load_image_from_bytes(image_data)
    if img is None:
        return None

    max_bytes = max_kb * 1024

    # 2. Compress the image iteratively
    compressed_data = _iterative_compress(img, max_bytes, format)
    if compressed_data is None:
        return None

    # 3. Encode the compressed binary data to Base64
    return _encode_to_base64(compressed_data)


def _load_image_from_url(url: str) -> Optional[Image.Image]:
    """Fetches and loads an image from a URL into a PIL Image object."""
    try:
        response = requests.get(url, stream=True, timeout=15)
        response.raise_for_status()
        image_data = response.content
        return _load_image_from_bytes(image_data)

    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL '{url}': {e}")
        return None
    except Exception as e:
        print(f"Error processing image from URL: {e}")
        return None


def _load_image_from_bytes(image_data: bytes) -> Optional[Image.Image]:
    """Loads an image from raw binary data into a PIL Image object."""
    try:
        img = Image.open(io.BytesIO(image_data))

        # Convert to RGB to ensure compatibility with JPEG compression (handles transparency)
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")

        return img

    except Exception as e:
        print(f"Error loading image from binary data: {e}")
        return None


def _iterative_compress(img: Image.Image, max_bytes: int, format: str, initial_quality: int = 95) -> Optional[bytes]:
    """
    Iteratively compresses a PIL Image until its size is <= max_bytes.
    Returns the compressed image binary data.
    """
    quality = initial_quality

    for _attempt in range(20):  # Limit to 20 attempts
        output_buffer = io.BytesIO()

        # Save the image to the in-memory buffer with the current quality setting
        img.save(output_buffer, format=format, quality=quality, optimize=True)

        compressed_data = output_buffer.getvalue()
        current_size = len(compressed_data)

        # Check if the size is acceptable
        if current_size <= max_bytes:
            return compressed_data

        # If the size is too large, decrease quality and try again
        quality -= 5

        if quality < 10:
            # Fallback for images that can't meet the target size even at low quality
            print(
                f"Warning: Minimum quality (10) reached. Final size: {current_size / 1024:.2f} KB (Target: {max_bytes / 1024:.2f} KB)"
            )
            return compressed_data  # Return the best effort


def _encode_to_base64(binary_data: bytes) -> str:
    """Encodes binary image data into a Base64 string."""
    base64_encoded_data = base64.b64encode(binary_data)
    # Decode from bytes to a standard string
    return base64_encoded_data.decode("utf-8")
