import tempfile
import unittest
from pathlib import Path
from PIL import Image
from wakamaria.image_processing import prepare_for_ocr

class ImageProcessingTest(unittest.TestCase):
    def test_upscales_and_keeps_grayscale(self):
        with tempfile.TemporaryDirectory() as d:
            src, dst = Path(d)/'in.png', Path(d)/'out.png'
            Image.new('RGB', (40, 20), 'white').save(src)
            prepare_for_ocr(src, dst)
            with Image.open(dst) as out:
                self.assertEqual(out.size, (120, 60))
                self.assertEqual(out.mode, 'L')

    def test_rejects_unsupported_format(self):
        with tempfile.TemporaryDirectory() as d:
            src, dst = Path(d)/'in.gif', Path(d)/'out.png'
            Image.new('RGB', (4, 4), 'white').save(src)
            with self.assertRaises(ValueError):
                prepare_for_ocr(src, dst)
