"""Optional OCR transcription. Admin must manually review and enter predictions."""
import os
import shutil
import subprocess
import tempfile
from PIL import UnidentifiedImageError
from wakamaria.image_processing import prepare_for_ocr
import frappe
from frappe import _

@frappe.whitelist()
def extract_screenshot(name):
    doc = frappe.get_doc("Wakamaria Screenshot", name)
    doc.check_permission("write")
    if not doc.image or not doc.image.startswith("/private/files/"):
        frappe.throw(_("Attach the screenshot as a private file first."))
    files = frappe.get_all("File", filters={"file_url":doc.image, "is_private":1, "attached_to_doctype":"Wakamaria Screenshot", "attached_to_name":doc.name}, pluck="name", limit_page_length=1)
    if not files:
        frappe.throw(_("Private screenshot must be attached to this record."))
    f = frappe.get_doc("File", files[0]); path = f.get_full_path()
    if os.path.splitext(path)[1].lower() not in (".png", ".jpg", ".jpeg", ".webp") or os.path.getsize(path)>8*1024*1024:
        frappe.throw(_("Use a PNG, JPG, or WebP image under 8 MB."))
    binary = shutil.which("tesseract")
    if not binary: frappe.throw(_("Tesseract OCR is not installed on the server."))
    try:
        with tempfile.TemporaryDirectory(prefix="wakamaria-ocr-") as temp_dir:
            prepared = os.path.join(temp_dir, "prepared.png")
            prepare_for_ocr(path, prepared)
            result = subprocess.run([binary, prepared, "stdout", "--psm", "6"], capture_output=True, text=True, timeout=45, check=True)
    except (subprocess.SubprocessError, OSError, UnidentifiedImageError, ValueError):
        frappe.throw(_("OCR failed, timed out or the image was invalid. Try a clearer, smaller screenshot."))
    doc.extracted_text = result.stdout[:100000]
    doc.save()
    return doc.extracted_text
