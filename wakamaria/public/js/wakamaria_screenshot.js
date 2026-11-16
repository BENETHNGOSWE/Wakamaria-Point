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
    frm.add_custom_button(__('Select complete rows'), () => {
      const rows = (frm.doc.review_rows || []).filter(r => !r.imported_match);
      const ready = rows.filter(r => r.league && r.home_team && r.away_team && r.kickoff && r.prediction);
      const missing = rows.length - ready.length;
      if (!ready.length) {
        frappe.msgprint(__('No complete rows found. Each row needs a league, both teams, kickoff and prediction.'));
        return;
      }
      frappe.confirm(
        __(`Select ${ready.length} complete row(s) for draft import? ${missing} incomplete row(s) will be skipped. Complete does not mean OCR is correct: review the values before creating drafts.`),
        async () => {
          for (const row of ready) await frappe.model.set_value(row.doctype, row.name, 'select_for_import', 1);
          frm.refresh_field('review_rows');
          frappe.msgprint(__('Complete rows selected. Review them and save the screenshot before creating drafts.'));
        }
      );
    });
    frm.add_custom_button(__('Mark highlighted rows for import'), () => {
      const rows = frm.fields_dict.review_rows.grid.get_selected_children().filter(r => !r.imported_match);
      if (!rows.length) { frappe.msgprint(__('Use the far-left table checkboxes to highlight one or more unimported rows first.')); return; }
      frappe.confirm(__(`Mark ${rows.length} highlighted row(s) for import? All selected rows must be completed and checked before creating drafts.`), async () => {
        for (const row of rows) await frappe.model.set_value(row.doctype, row.name, 'select_for_import', 1);
        frm.refresh_field('review_rows');
        frappe.msgprint(__('Highlighted rows marked. Complete and review them, then save before creating drafts.'));
      });
    });
    frm.add_custom_button(__('Create draft matches'), () => {
      if (frm.is_dirty()) { frappe.msgprint(__('Save your review changes first.')); return; }
      frappe.confirm(__('Create unpublished draft matches from selected rows? Verify every field first.'), () => {
        frappe.call({method:'wakamaria.ocr.create_drafts',args:{name:frm.doc.name},freeze:true,callback(r){frm.reload_doc();frappe.msgprint(__(`${r.message.length} draft match(es) created. Open each draft to confirm its provider fixture and publish it.`));}});
      });
    });
  }
});
