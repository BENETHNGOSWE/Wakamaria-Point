"""Private screenshot OCR, review and import. Nothing is published automatically."""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from PIL import UnidentifiedImageError
import frappe
from frappe import _
from wakamaria.card_ocr import extract_cards, parse_tip, parse_teams, MAX_CARDS, TIPS
from wakamaria.image_processing import prepare_for_ocr


def screenshot_file(doc):
    if not doc.image or not doc.image.startswith('/private/files/'):
        frappe.throw(_('Attach the screenshot as a private file first.'))
    files=frappe.get_all('File', filters={'file_url':doc.image,'is_private':1,'attached_to_doctype':'Wakamaria Screenshot','attached_to_name':doc.name}, pluck='name', limit_page_length=1)
    if not files: frappe.throw(_('Private screenshot must be attached to this record.'))
    path=frappe.get_doc('File',files[0]).get_full_path()
    if os.path.splitext(path)[1].lower() not in ('.png','.jpg','.jpeg','.webp') or os.path.getsize(path)>8*1024*1024:
        frappe.throw(_('Use a PNG, JPG, or WebP image under 8 MB.'))
    return path

def ocr_config():
    binary=shutil.which('tesseract')
    if not binary: frappe.throw(_('Tesseract OCR is not installed on the server.'))
    model_dir=frappe.db.get_single_value('Wakamaria Settings', 'ocr_tessdata_dir')
    if model_dir:
        model_dir=os.path.expanduser(model_dir.strip())
        if not os.path.isabs(model_dir) or not os.path.isfile(os.path.join(model_dir, 'eng.traineddata')):
            frappe.throw(_('OCR Model Directory must be an absolute path containing eng.traineddata.'))
    return binary, model_dir or None

def tesseract(binary, path, model_dir):
    args=[binary,path,'stdout','-l','eng','--psm','6']
    if model_dir: args.extend(['--tessdata-dir',model_dir])
    return subprocess.run(args,capture_output=True,text=True,timeout=45,check=True).stdout[:100000]

@frappe.whitelist(methods=['POST'])
def extract_screenshot(name):
    doc=frappe.get_doc('Wakamaria Screenshot',name);doc.check_permission('write')
    path=screenshot_file(doc);binary,model_dir=ocr_config()
    try:
        with tempfile.TemporaryDirectory(prefix='wakamaria-ocr-') as tmp:
            prepared=os.path.join(tmp,'prepared.png');prepare_for_ocr(path,prepared)
            result=tesseract(binary,prepared,model_dir)
    except (subprocess.SubprocessError, OSError, UnidentifiedImageError, ValueError):
        frappe.throw(_('OCR failed, timed out, or the image was invalid.'))
    doc.extracted_text=result;doc.save();return result

@frappe.whitelist(methods=['POST'])
def prepare_review(name):
    doc=frappe.get_doc('Wakamaria Screenshot',name);doc.check_permission('write')
    if doc.review_rows:
        frappe.throw(_('Review rows already exist. To avoid losing changes, use a new Screenshot record or clear the table and save first.'))
    path=screenshot_file(doc);binary,model_dir=ocr_config()
    try:
        with tempfile.TemporaryDirectory(prefix='wakamaria-cards-') as tmp:
            cards,total=extract_cards(path,binary,tmp,model_dir)
    except (subprocess.SubprocessError, OSError, UnidentifiedImageError, ValueError):
        frappe.throw(_('Card OCR failed or timed out. Check your image, Tesseract, and model configuration.'))
    if not cards:
        frappe.throw(_('No compatible match cards detected. Use a clear full screenshot with at least two matching league headers, or enter rows manually.'))
    leagues=frappe.get_all('Wakamaria League', filters={'enabled':1}, fields=['name','league_name'])
    for card in cards:
        text=card['card_text']; home,away=parse_teams(text)
        # Only unambiguous full league names are suggested. Many OCR typos and
        # unconfigured leagues will be intentionally left blank for review.
        matches=[league.name for league in leagues if league.league_name.casefold() in text.casefold()]
        doc.append('review_rows', {'league':matches[0] if len(matches)==1 else None,
                   'home_team':home, 'away_team':away,
                   'prediction':parse_tip(card['tip_text']) or parse_tip(text),
                   'card_ocr':text[:4000], 'tip_ocr':card['tip_text'][:500],
                   'select_for_import':0})
    doc.save()
    return {'created':len(cards),'detected':total,'limit':MAX_CARDS}

@frappe.whitelist(methods=['POST'])
def create_drafts(name):
    if not frappe.has_permission('Wakamaria Match', 'create'):
        frappe.throw(_('You do not have permission to create matches.'), frappe.PermissionError)
    # Serialize imports for this screenshot to prevent duplicate button clicks.
    frappe.db.sql('SELECT name FROM `tabWakamaria Screenshot` WHERE name = %s FOR UPDATE', (name,))
    doc=frappe.get_doc('Wakamaria Screenshot',name);doc.check_permission('write')
    rows=[r for r in doc.review_rows if r.select_for_import and not r.imported_match]
    if not rows: frappe.throw(_('Select at least one unimported review row.'))
    seen = set()
    for row in rows:
        if not all((row.league,row.home_team,row.away_team,row.kickoff,row.prediction)):
            frappe.throw(_('Row {0}: complete league, both teams, kickoff and prediction before importing.').format(row.idx))
        if row.prediction not in TIPS:
            frappe.throw(_('Row {0}: unsupported prediction.').format(row.idx))
        if not frappe.db.exists('Wakamaria League', {'name':row.league,'enabled':1}):
            frappe.throw(_('Row {0}: choose an enabled league.').format(row.idx))
        filters={'league':row.league,'home_team':row.home_team.strip(),'away_team':row.away_team.strip(),'kickoff':row.kickoff}
        key=(row.league,row.home_team.strip().casefold(),row.away_team.strip().casefold(),str(row.kickoff))
        if key in seen:
            frappe.throw(_('Row {0}: duplicates another selected review row.').format(row.idx))
        seen.add(key)
        if frappe.db.exists('Wakamaria Match',filters):
            frappe.throw(_('Row {0}: a match with the same league, teams and kickoff already exists.').format(row.idx))
    created=[]
    for row in rows:
        match=frappe.get_doc({'doctype':'Wakamaria Match','league':row.league,'home_team':row.home_team.strip(),
                              'away_team':row.away_team.strip(),'kickoff':row.kickoff,'prediction':row.prediction,'published':0})
        match.insert();row.imported_match=match.name;row.select_for_import=0;created.append(match.name)
    doc.save()
    return created
