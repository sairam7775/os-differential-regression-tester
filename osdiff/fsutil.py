"""Shared artifact writing, best-effort POSIX permissions, and screenshot masking.

This is not a complete artifact privacy boundary: callers can persist sensitive
metadata elsewhere, Windows ACLs are not configured, and literal XML redaction
currently corrupts attribute syntax. See docs/BASELINE_ASSESSMENT.md.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def private_dir(path):
    """Create a directory and best-effort chmod 0700 on POSIX; Windows inherits existing ACLs."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        try:
            os.chmod(path, 0o700)
        except OSError:
            pass
    return path


def private_file(path):
    """Best-effort chmod an existing POSIX artifact to 0600; permission errors are swallowed."""
    path = Path(path)
    if os.name != "nt" and path.exists():
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return path


def write_text(path, text, *, encoding="utf-8"):
    """Create the artifact's parent, write UTF-8 text, and apply best-effort private permissions."""
    path = Path(path)
    private_dir(path.parent)
    path.write_text(text, encoding=encoding)
    private_file(path)
    return path


def write_json(path, value):
    """Serialize indented JSON through write_text; callers must sanitize sensitive values first."""
    return write_text(path, json.dumps(value, indent=2), encoding="utf-8")


def redact_values(text, values):
    """Replace literal secret substrings; this is not XML-aware or structured-field sanitization.
    
    The literal <REDACTED> marker can invalidate XML attributes, and encoded secrets
    are not matched. This known defect is documented rather than fixed here."""
    result = str(text or "")
    for value in values or []:
        if value:
            result = result.replace(str(value), "<REDACTED>")
    return result


def mask_image_regions(path, regions):
    """Overwrite configured screenshot rectangles in place and reapply private permissions.
    
    Normalized coordinates use image dimensions. No regions means no screenshot
    redaction; region validation and Windows ACL protection are not provided here."""
    if not regions:
        return
    from PIL import Image, ImageDraw
    path = Path(path)
    with Image.open(path).convert("RGB") as img:
        draw = ImageDraw.Draw(img)
        width, height = img.size
        for region in regions:
            if region.get("normalized"):
                x1 = int(float(region.get("x", 0)) * width)
                y1 = int(float(region.get("y", 0)) * height)
                x2 = int((float(region.get("x", 0)) + float(region.get("width", 0))) * width)
                y2 = int((float(region.get("y", 0)) + float(region.get("height", 0))) * height)
            else:
                x1 = int(region.get("x", 0)); y1 = int(region.get("y", 0))
                x2 = x1 + int(region.get("width", 0)); y2 = y1 + int(region.get("height", 0))
            draw.rectangle((x1, y1, x2, y2), fill=(0, 0, 0))
        img.save(path)
    private_file(path)
