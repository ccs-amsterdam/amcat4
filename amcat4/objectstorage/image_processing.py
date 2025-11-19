"""Utility functions for processing small images like icons and thumbnaile"""

import base64
import hashlib
import io

import httpx
from PIL import Image

from amcat4.models import ImageObject


async def create_image_from_url(url: str | None) -> ImageObject | None:
    if url is None:
        return None

    try:
        base64 = await _compress_image_from_url_to_base64(url)
        hash = hashlib.sha256(base64.encode("utf-8")).hexdigest() if base64 else "missing"
        return ImageObject(id=hash[:16], base64=base64)
    except Exception as e:
        print(f"Error creating image from URL '{url}': {e}")
        return None


async def _compress_image_from_url_to_base64(
    url: str, max_kb: int = 100, format: str = "JPEG", max_download_kb: int = 1024 * 10
) -> str:
    """
    Loads an image from a URL, compresses it, and returns the Base64 string.
    """
    img = await _load_image_from_url(url, max_download_kb * 1024)
    compressed_data = _iterative_compress(img, max_kb * 1024, format)
    return _encode_to_base64(compressed_data)


def _compress_image_from_bytes_to_base64(image_data: bytes, max_kb: int = 100, format: str = "JPEG") -> str:
    """
    Loads an image from binary data, compresses it, and returns the Base64 string.
    """
    img = _load_image_from_bytes(image_data)
    compressed_data = _iterative_compress(img, max_kb * 1024, format)
    return _encode_to_base64(compressed_data)


async def _load_image_from_url(url: str, max_bytes: int) -> Image.Image:
    """Fetches and loads an image from a URL into a PIL Image object."""
    image_data = await _chunked_download(url, max_bytes)
    return _load_image_from_bytes(image_data)


async def _chunked_download(url: str, max_bytes: int, chunk_size=8192):
    """for downloading with max size limit"""
    chunks: list[bytes] = []
    current_size = 0

    async with httpx.AsyncClient() as client:
        async with client.stream("GET", url) as r:
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


def _load_image_from_bytes(image_data: bytes, max_height=2000, max_width=2000) -> Image.Image:
    """Loads an image from raw binary data into a PIL Image object."""

    allowed_mime_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]

    img = Image.open(io.BytesIO(image_data))
    width, height = img.size

    if width > max_width or height > max_height:
        raise ValueError(f"Image dimensions {width}x{height} exceed maximum allowed size of {max_width}x{max_height}.")

    if img.get_format_mimetype() not in allowed_mime_types:
        raise ValueError(
            f"Error: Unsupported image MIME type '{img.get_format_mimetype()}'. Has to be one of {', '.join(allowed_mime_types)}."
        )

    # Convert to RGB to ensure compatibility with JPEG compression (handles transparency)
    if img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")

    return img


def _iterative_compress(img: Image.Image, max_bytes: int, format: str, initial_quality: int = 95) -> bytes:
    """
    Iteratively compresses a PIL Image until its size is <= max_bytes.
    Returns the compressed image binary data.
    """
    quality = initial_quality
    compressed_data: bytes = b""

    for _iter in range(20):
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

    return compressed_data  # Return the best effort


def _encode_to_base64(binary_data: bytes) -> str:
    """Encodes binary image data into a Base64 string."""
    base64_encoded_data = base64.b64encode(binary_data)
    # Decode from bytes to a standard string
    return base64_encoded_data.decode("utf-8")
