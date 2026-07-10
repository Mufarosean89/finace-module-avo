"""
Image-processing service.

Uses Pillow to:
* Compress / optimise receipt and document photos
* Resize large images to a configurable max dimension
* Generate square-ish thumbnails for previews
* Detect whether a file is a processable image
"""
from __future__ import annotations

import io
import logging
import os

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile

logger = logging.getLogger(__name__)

# ── Supported image types ─────────────────────────────────
SUPPORTED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tiff'}
SUPPORTED_IMAGE_MIMES = {
    'image/jpeg', 'image/png', 'image/webp', 'image/gif',
    'image/bmp', 'image/tiff',
}


def is_processable_image(file_obj) -> bool:
    """
    Detect whether *file_obj* is an image we can process.

    Checks both the MIME type (content_type attribute) and
    the file extension as a fallback.
    """
    # Try content-type
    ct = getattr(file_obj, 'content_type', '') or ''
    if ct.lower() in SUPPORTED_IMAGE_MIMES:
        return True

    # Fallback: extension
    name = getattr(file_obj, 'name', '') or ''
    ext = os.path.splitext(name)[1].lower()
    return ext in SUPPORTED_IMAGE_EXTENSIONS


def process_uploaded_image(
    uploaded_file: UploadedFile,
    *,
    max_width: int = None,
    thumb_width: int = None,
    quality: int = 85,
) -> dict:
    """
    Process an uploaded image file.

    Opens the image with Pillow, resizes it if it exceeds *max_width*,
    compresses it as JPEG/WebP, and generates a thumbnail at *thumb_width*.

    Parameters
    ----------
    uploaded_file : UploadedFile
        The file uploaded via the request.
    max_width : int, optional
        Maximum width in pixels for the full-size image.
        Defaults to ``settings.ATTACHMENT_FULL_WIDTH`` (1920).
    thumb_width : int, optional
        Width in pixels for the generated thumbnail.
        Defaults to ``settings.ATTACHMENT_THUMB_WIDTH`` (300).
    quality : int
        JPEG/WebP compression quality (1–100). Default 85.

    Returns
    -------
    dict
        ``{'full': ContentFile, 'thumb': ContentFile | None,
        'is_image': True}``
        or ``{'full': None, 'thumb': None, 'is_image': False}``
        if the file is not a processable image.
    """
    if not is_processable_image(uploaded_file):
        return {'full': None, 'thumb': None, 'is_image': False}

    max_width = max_width or getattr(settings, 'ATTACHMENT_FULL_WIDTH', 1920)
    thumb_width = thumb_width or getattr(settings, 'ATTACHMENT_THUMB_WIDTH', 300)

    try:
        from PIL import Image, ImageOps
    except ImportError:
        logger.warning('Pillow is not installed — returning original file unprocessed')
        uploaded_file.seek(0)
        raw = uploaded_file.read()
        return {
            'full': ContentFile(raw),
            'thumb': None,
            'is_image': True,
        }

    uploaded_file.seek(0)
    try:
        img = Image.open(uploaded_file)
    except Exception as exc:
        logger.error('Failed to open uploaded image: %s', exc)
        uploaded_file.seek(0)
        raw = uploaded_file.read()
        return {
            'full': ContentFile(raw),
            'thumb': None,
            'is_image': True,
        }

    # ── Convert to RGB (required for JPEG) ────────────────
    if img.mode in ('RGBA', 'LA', 'P'):
        img = img.convert('RGB')

    # ── Resize (preserve aspect ratio) ────────────────────
    orig_w, orig_h = img.size
    if max_width and orig_w > max_width:
        ratio = max_width / orig_w
        new_h = int(orig_h * ratio)
        img = img.resize((max_width, new_h), Image.LANCZOS)

    # ── Save compressed full version ──────────────────────
    full_buffer = io.BytesIO()
    save_kwargs = _get_save_kwargs(uploaded_file, quality)
    img.save(full_buffer, **save_kwargs)
    full_content = ContentFile(full_buffer.getvalue())

    # ── Generate thumbnail ────────────────────────────────
    thumb_content = None
    if thumb_width:
        uploaded_file.seek(0)
        try:
            thumb_img = Image.open(io.BytesIO(uploaded_file.read()))
            if thumb_img.mode in ('RGBA', 'LA', 'P'):
                thumb_img = thumb_img.convert('RGB')
        except Exception:
            thumb_img = img.copy()

        thumb_img.thumbnail((thumb_width, thumb_width), Image.LANCZOS)

        thumb_buffer = io.BytesIO()
        thumb_save_kwargs = _get_save_kwargs(uploaded_file, quality)
        thumb_img.save(thumb_buffer, **thumb_save_kwargs)
        thumb_content = ContentFile(thumb_buffer.getvalue())

    return {
        'full': full_content,
        'thumb': thumb_content,
        'is_image': True,
    }


def _get_save_kwargs(uploaded_file, quality: int) -> dict:
    """
    Return appropriate Pillow ``save()`` kwargs based on content type.

    JPEG and WebP get quality-controlled compression; PNG gets
    ``optimize=True``.
    """
    ct = getattr(uploaded_file, 'content_type', '') or ''
    ext = os.path.splitext(getattr(uploaded_file, 'name', '') or '')[1].lower()

    if 'webp' in ct or ext == '.webp':
        return {'format': 'WEBP', 'quality': quality}
    if 'png' in ct or ext == '.png':
        return {'format': 'PNG', 'optimize': True}
    # Default: JPEG
    return {'format': 'JPEG', 'quality': quality, 'optimize': True}
