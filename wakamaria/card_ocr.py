"""Best-effort card segmentation and OCR. All output MUST be reviewed by a human.

The card detector is deliberately conservative and layout-specific. It returns
no cards for layouts it does not recognise rather than inventing predictions.
"""
from __future__ import annotations
import re
import math
import statistics
import subprocess
from pathlib import Path
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

MAX_CARDS = 8
MAX_PIXELS = 12_000_000
TIPS = ('Over 2.5', 'Under 2.5', 'BTTS Yes', 'BTTS No', '1X', 'X2', '12', '1', 'X', '2')

def detect_cards(image):
    """Find broad light-grey competition headers typical of the reference app."""
    image = image.convert('RGB')
    width, height = image.size
    if width < 300 or height < 300 or width * height > MAX_PIXELS:
        return []
    step = max(2, width // 200)
    runs = []
    current = []
    for y in range(int(height * .06), int(height * .92)):
        pixels = [image.getpixel((x, y)) for x in range(int(width * .20), int(width * .80), step)]
        ratio = sum(195 <= r <= 245 and max(r, g, b) - min(r, g, b) <= 6 for r, g, b in pixels) / len(pixels)
        if ratio >= .83:
            if current and y - current[-1] > max(5, round(height * .010)):
                runs.append(current); current = []
            current.append(y)
    if current: runs.append(current)
    groups = [(g[0], g[-1]) for g in runs if len(g) >= max(10, int(height*.012)) and g[-1]-g[0] <= height*.12]
    # A layout with fewer than two similarly spaced bars is too ambiguous.
    if len(groups) < 2:
        return []
    gaps = [groups[i+1][0] - groups[i][0] for i in range(len(groups)-1)]
    spacing = statistics.median(gaps)
    if spacing < height*.06 or spacing > height*.45:
        return []
    # Avoid treating unrelated blocks as match cards.
    if sum(abs(gap-spacing) <= spacing*.30 for gap in gaps) < max(1, len(gaps)-1):
        return []
    cards=[]
    for i, (start, end_header) in enumerate(groups):
        end = groups[i+1][0] if i+1 < len(groups) else min(height, round(start+spacing))
        if end <= end_header + 10: continue
        remain = end-end_header
        cards.append({'card':(0, max(0,start-4), width, end),
                      'tip':(round(width*.275), round(end_header + remain*.32), round(width*.75), round(end_header + remain*.64))})
    return cards

def prepare_crop(image, box, scale):
    crop = ImageOps.grayscale(image.crop(box))
    crop = ImageOps.autocontrast(crop, cutoff=1)
    scale = min(scale, math.sqrt(24_000_000 / (crop.width * crop.height)))
    crop = crop.resize((max(1, int(crop.width * scale)), max(1, int(crop.height * scale))), Image.Resampling.LANCZOS)
    return ImageEnhance.Contrast(crop).enhance(1.2).filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))

def recognise(binary, path, psm, tessdata_dir=None):
    command=[binary, str(path), 'stdout', '-l', 'eng', '--psm', str(psm)]
    if tessdata_dir:
        command += ['--tessdata-dir', str(tessdata_dir)]
    return subprocess.run(command, capture_output=True, text=True, timeout=30, check=True).stdout[:15000]

def extract_cards(path, binary, tmpdir, tessdata_dir=None):
    with Image.open(path) as img:
        if img.format not in ('PNG', 'JPEG', 'WEBP') or img.width*img.height > MAX_PIXELS:
            raise ValueError('Unsupported image or dimensions')
        image = ImageOps.exif_transpose(img).convert('RGB')
        boxes = detect_cards(image)
        result=[]
        for i, box in enumerate(boxes[:MAX_CARDS]):
            card_path=Path(tmpdir)/f'card-{i}.png'
            tip_path=Path(tmpdir)/f'tip-{i}.png'
            prepare_crop(image, box['card'], 3).save(card_path)
            prepare_crop(image, box['tip'], 5).save(tip_path)
            card_text=recognise(binary, card_path, 6, tessdata_dir)
            tip_text=recognise(binary, tip_path, 6, tessdata_dir)
            result.append({'card_text':card_text, 'tip_text':tip_text})
        return result, len(boxes)

def parse_tip(text):
    # Never guess ambiguous OCR such as "Overs" or a bare number.
    match = re.search(r'\btip\s*[:;]\s*(over\s*2[.,]5|under\s*2[.,]5|btts\s*(?:yes|no)|1x|x2|12|1|x|2)(?=\s|$|[^\w.])', text, re.I)
    if not match:
        return ''
    value = re.sub(r'\s+', ' ', match.group(1)).replace(',', '.').lower()
    return {x.lower():x for x in TIPS}.get(value, '')

def parse_teams(text):
    # Heuristic only; badges/flags can look like letters. Always review.
    for line in text.splitlines():
        if re.search(r'half.?time|tip\s*:|odds|view details', line, re.I): continue
        match = re.match(r'^\s*(.+?)\s+\d+\s*[-:]\s*\d+\s+(.+?)\s*$', line)
        if not match:
            match = re.match(r'^\s*(.+?)\s+vs\.?\s+(.+?)\s*$', line, re.I)
        if match:
            home,away = [re.sub(r'^[^A-Za-z]+|[^A-Za-z]+$', '', s).strip() for s in match.groups()]
            if len(home)>=2 and len(away)>=2 and len(home)<=80 and len(away)<=80:
                return home, away
    return '', ''
