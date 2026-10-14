"""Shared artifact writing, best-effort POSIX permissions, and screenshot masking.

This is not a complete artifact privacy boundary: callers can persist sensitive
metadata elsewhere, Windows ACLs are not configured, and literal XML redaction
currently corrupts attribute syntax. See docs/BASELINE_ASSESSMENT.md.
"""

from __future__ import annotations

import json
import html
import os
from pathlib import Path
from xml.etree import ElementTree as ET


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


def write_json(path, value, *, sensitive_values=None):
    """Serialize indented JSON through write_text; callers must sanitize sensitive values first."""
    return write_text(path, json.dumps(redact_data(value, sensitive_values), indent=2), encoding="utf-8")


def redact_values(text, values):
    """Redact raw and HTML-escaped secrets using a marker safe inside XML attributes."""
    result = str(text or "")
    for value in sorted({str(v) for v in (values or []) if v}, key=len, reverse=True):
        if value:
            for representation in {value, html.escape(value), html.escape(value, quote=False)}:
                result = result.replace(representation, "[REDACTED]")
    return result


def redact_data(value, values):
    """Sanitize nested artifact strings without changing list/dict/scalar types."""
    if isinstance(value, str):
        return redact_values(value, values)
    if isinstance(value, dict):
        return {redact_values(k, values) if isinstance(k, str) else k: redact_data(v, values) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_data(v, values) for v in value]
    return value


def redact_xml(source, values):
    """Redact decoded XML attributes/text and serialize well-formed XML again.

    Malformed input stays malformed (and thus INVALID), with secrets still removed.
    Never repair a broken capture into apparently valid comparison evidence.
    """
    try:
        root = ET.fromstring(source)
    except ET.ParseError:
        return redact_values(source, values)
    for node in root.iter():
        node.attrib.update({key: redact_values(value, values) for key, value in node.attrib.items()})
        if node.text:
            node.text = redact_values(node.text, values)
        if node.tail:
            node.tail = redact_values(node.tail, values)
    return ET.tostring(root, encoding="unicode")


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
