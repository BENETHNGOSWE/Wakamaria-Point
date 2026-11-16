"""Bounded screenshot preparation for OCR. Does not retain transformed images."""
from math import sqrt
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

MAX_INPUT_PIXELS = 12_000_000
MAX_OUTPUT_PIXELS = 24_000_000

def prepare_for_ocr(source, destination):
    with Image.open(source) as image:
        if image.format not in ('PNG', 'JPEG', 'WEBP'):
            raise ValueError('Unsupported image format')
        if image.width * image.height > MAX_INPUT_PIXELS:
            raise ValueError('Image dimensions are too large')
        image = ImageOps.exif_transpose(image)
        image = ImageOps.grayscale(image)
        image = ImageOps.autocontrast(image, cutoff=1)
        scale = min(3.0, sqrt(MAX_OUTPUT_PIXELS / (image.width * image.height)))
        size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
        image = image.resize(size, Image.Resampling.LANCZOS)
        image = ImageEnhance.Contrast(image).enhance(1.2)
        image = image.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))
        image.save(destination, format='PNG')
