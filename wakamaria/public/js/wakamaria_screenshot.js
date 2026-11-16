frappe.ui.form.on('Wakamaria Screenshot', {
  refresh(frm) {
    if (frm.is_new()) return;
    frm.add_custom_button(__('Extract text with OCR'), () => {
      if (frm.is_dirty()) { frappe.msgprint(__('Save your changes first.')); return; }
      frappe.call({method:'wakamaria.ocr.extract_screenshot',args:{name:frm.doc.name},freeze:true,freeze_message:__('Reading screenshot...'),callback(){frm.reload_doc();frappe.msgprint(__('Raw text extracted. It is not published.'));}});
    });
    frm.add_custom_button(__('Prepare match review'), () => {
      if (frm.is_dirty()) { frappe.msgprint(__('Save your changes first.')); return; }
      frappe.call({method:'wakamaria.ocr.prepare_review',args:{name:frm.doc.name},freeze:true,freeze_message:__('Reading match cards. This may take a minute...'),callback(r){frm.reload_doc();let d=r.message;frappe.msgprint(__(`Prepared ${d.created} review rows (${d.detected} detected). Verify EVERY field, including names and tip. Set the league and kickoff, select rows and save. Nothing is published.`));}});
    });
    frm.add_custom_button(__('Refresh suggestions'), () => {
      if (frm.is_dirty()) { frappe.msgprint(__('Save your changes first.')); return; }
      frappe.call({method:'wakamaria.ocr.refresh_suggestions',args:{name:frm.doc.name},freeze:true,callback(r){frm.reload_doc();frappe.msgprint(__(`${r.message.fields_filled} empty field(s) filled from saved OCR. Existing values were not changed. Verify all suggestions before import.`));}});
    });
    frm.add_custom_button(__('Create draft matches'), () => {
      if (frm.is_dirty()) { frappe.msgprint(__('Save your review changes first.')); return; }
      frappe.confirm(__('Create unpublished draft matches from selected rows? Verify every field first.'), () => {
        frappe.call({method:'wakamaria.ocr.create_drafts',args:{name:frm.doc.name},freeze:true,callback(r){frm.reload_doc();frappe.msgprint(__(`${r.message.length} draft match(es) created. Open each draft to confirm its provider fixture and publish it.`));}});
      });
    });
  }
});
