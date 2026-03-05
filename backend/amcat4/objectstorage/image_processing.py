"""Utility functions for processing small images like icons and thumbnaile"""

import base64
import hashlib
import io

from PIL import Image

from amcat4.connections import http
from amcat4.models import ImageObject


async def create_image_from_url(url: str | None, max_download_kb: int = 1024 * 10) -> ImageObject | None:
    if url is None:
        return None

    try:
        img = await _load_image_from_url(url, max_download_kb * 1024)
        return _create_image_object(img)
    except Exception as e:
        raise ValueError(f"Error creating image from URL '{url}': {e}") from e


async def create_image_from_bytes(image_data: bytes) -> ImageObject | None:
    try:
        img = _load_image_from_bytes(image_data)
        return _create_image_object(img)
    except Exception as e:
        raise ValueError(f"Error creating image from uploaded data': {e}") from e


def _create_image_object(img: Image.Image) -> ImageObject:
    base64 = _compress_image_to_base64(img)
    hash = hashlib.sha256(base64.encode("utf-8")).hexdigest() if base64 else "missing"
    return ImageObject(id=hash[:16], base64=base64)


def _compress_image_to_base64(image: Image.Image, max_kb: int = 100, format: str = "JPEG") -> str:
    """
    Compresses an image and returns the Base64 string.
    """
    compressed_data = _iterative_compress(image, max_kb * 1024, format, max_quality=90)
    return _encode_to_base64(compressed_data)


async def _load_image_from_url(url: str, max_bytes: int) -> Image.Image:
    """Fetches and loads an image from a URL into a PIL Image object."""
    image_data = await _chunked_download(url, max_bytes)
    return _load_image_from_bytes(image_data, max_bytes)


async def _chunked_download(url: str, max_bytes: int, chunk_size=8192):
    """for downloading with max size limit"""
    chunks: list[bytes] = []
    current_size = 0

    async with http().stream("GET", url) as r:
        r.raise_for_status()

        content_length = r.headers.get("Content-Length")
        if content_length and int(content_length) > max_bytes:
            raise ValueError(f"Error : Image at URL '{url}' exceeds maximum allowed size of {max_bytes} bytes.")

        async for chunk in r.aiter_bytes(chunk_size=chunk_size):
            chunks.append(chunk)
            current_size += len(chunk)
            if current_size > max_bytes:
                raise ValueError(
                    f"Error: Image at URL '{url}' exceeds maximum allowed size of {max_bytes} bytes during download."
                )

    return b"".join(chunks)


def _load_image_from_bytes(image_data: bytes, max_bytes: int | None = None) -> Image.Image:
    """Loads an image from raw binary data into a PIL Image object."""

    allowed_mime_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]

    img = Image.open(io.BytesIO(image_data))
    bytes = len(image_data)

    if max_bytes and bytes > max_bytes:
        raise ValueError(f"Image size {bytes / 1024:.2f} KB exceeds maximum allowed size of {max_bytes / 1024:.2f} KB.")

    if img.get_format_mimetype() not in allowed_mime_types:
        raise ValueError(
            f"Error: Unsupported image MIME type '{img.get_format_mimetype()}'. "
            f"Has to be one of {', '.join(allowed_mime_types)}."
        )

    # Convert to RGB to ensure compatibility with JPEG compression (handles transparency)
    if img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")

    return img


def _iterative_compress(
    img: Image.Image,
    max_bytes: int,
    format: str,
    initial_quality: int = 95,
    max_dim: tuple[float, float] = (600, 337.5),
    max_quality: int = 100,
) -> bytes:
    """
    Iteratively compresses a PIL Image until its size is <= max_bytes.
    Returns the compressed image binary data.
    """

    img.thumbnail(max_dim)
    quality = initial_quality
    compressed_data: bytes = b""

    for _iter in range(20):
        output_buffer = io.BytesIO()
        img.save(output_buffer, format=format, quality=quality, optimize=True)
        compressed_data = output_buffer.getvalue()
        current_size = len(compressed_data)

        # Check if the size is acceptable
        if current_size <= max_bytes and quality <= max_quality:
            return compressed_data

        quality -= 5
        if quality < 10:
            # Fallback for images that can't meet the target size even at low quality
            print(
                f"Warning: Minimum quality (10) reached. Final size: {current_size / 1024:.2f} KB "
                f"(Target: {max_bytes / 1024:.2f} KB)"
            )
            return compressed_data  # Return the best effort

    return compressed_data  # Return the best effort


def _encode_to_base64(binary_data: bytes) -> str:
    """Encodes binary image data into a Base64 string."""
    base64_encoded_data = base64.b64encode(binary_data)
    # Decode from bytes to a standard string
    return base64_encoded_data.decode("utf-8")
