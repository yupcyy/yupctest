import io

import pytest
from PIL import Image

from qq_deepseek.building.pixel_art import create_pixel_art


def test_pixel_art_is_bounded_and_png():
    source = io.BytesIO()
    Image.new("RGB", (1200, 600), (200, 80, 30)).save(source, "JPEG")
    result, size = create_pixel_art(source.getvalue())
    assert size == (100, 50)
    with Image.open(io.BytesIO(result)) as image:
        assert image.format == "PNG"
        assert image.size == size


def test_pixel_art_rejects_non_image():
    with pytest.raises(ValueError):
        create_pixel_art(b"not an image")
