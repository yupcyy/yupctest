from __future__ import annotations

import io

from PIL import Image, UnidentifiedImageError

MAX_SOURCE_PIXELS = 40_000_000
Image.MAX_IMAGE_PIXELS = MAX_SOURCE_PIXELS
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


def create_pixel_art(content: bytes, max_side: int = 100) -> tuple[bytes, tuple[int, int]]:
    """Decode an untrusted raster image and return a visibly pixelated PNG."""
    if not content:
        raise ValueError("empty image")
    try:
        with Image.open(io.BytesIO(content)) as source:
            if source.format not in ALLOWED_FORMATS:
                raise ValueError("only JPEG, PNG and WebP are accepted")
            if getattr(source, "is_animated", False):
                raise ValueError("animated images are not accepted")
            if source.width * source.height > MAX_SOURCE_PIXELS:
                raise ValueError("source image has too many pixels")
            source.load()
            image = source.convert("RGBA")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("invalid or unsafe image") from exc

    scale = min(1.0, max_side / max(image.size))
    target = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    # A small color grid followed by nearest-neighbour enlargement creates the
    # mosaic aesthetic without any model or external image service.
    grid = (max(1, (target[0] + 3) // 4), max(1, (target[1] + 3) // 4))
    reduced = image.resize(grid, Image.Resampling.LANCZOS)
    pixelated = reduced.resize(target, Image.Resampling.NEAREST)
    output = io.BytesIO()
    pixelated.save(output, format="PNG", optimize=True)
    return output.getvalue(), target
