frappe.ui.form.on('Wakamaria Screenshot', {
  refresh(frm) {
    if (frm.is_new()) return;
    frm.add_custom_button(__('Extract text with OCR'), () => {
      frappe.call({method:'wakamaria.ocr.extract_screenshot',args:{name:frm.doc.name},freeze:true,freeze_message:__('Reading screenshot...'),callback(){frm.reload_doc();frappe.msgprint(__('Review the text and manually create predictions. OCR does not publish matches.'));}});
    });
  }
});
