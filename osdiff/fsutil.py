from __future__ import annotations

import json
import os
from pathlib import Path


def private_dir(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        try:
            os.chmod(path, 0o700)
        except OSError:
            pass
    return path


def private_file(path):
    path = Path(path)
    if os.name != "nt" and path.exists():
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return path


def write_text(path, text, *, encoding="utf-8"):
    path = Path(path)
    private_dir(path.parent)
    path.write_text(text, encoding=encoding)
    private_file(path)
    return path


def write_json(path, value):
    return write_text(path, json.dumps(value, indent=2), encoding="utf-8")


def redact_values(text, values):
    result = str(text or "")
    for value in values or []:
        if value:
            result = result.replace(str(value), "<REDACTED>")
    return result


def mask_image_regions(path, regions):
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
