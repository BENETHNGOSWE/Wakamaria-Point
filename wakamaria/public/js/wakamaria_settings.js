frappe.ui.form.on('Wakamaria Settings', {
  refresh(frm) {
    frm.add_custom_button(__('Preview GOAL fixture matches'), () => {
      if (frm.is_dirty()) { frappe.msgprint(__('Save settings first.')); return; }
      frappe.call({method:'wakamaria.goal_preview.preview', freeze:true,
        freeze_message:__('Checking fixture candidates (no data will be changed)...'), callback(r) {
          if (!r.message) return;
          const data = r.message;
          const lines = [data.note, `Competition/date groups: ${data.groups}`,
            `Skipped (missing league ID or ambiguous local time): ${data.skipped}`,
            `Provider records not understood: ${data.unparsed}`, ''];
          for (const row of data.matches) {
            lines.push(`${row.home} vs ${row.away} (${row.kickoff_utc}) — ${row.status}${row.fixture_id ? ' [' + row.fixture_id + ']' : ''}`);
          }
          if (!data.matches.length) lines.push('No eligible unconfirmed matches to preview.');
          if (data.examples && data.examples.length) {
            lines.push('', 'Sanitized provider examples (no API key):', JSON.stringify(data.examples, null, 2));
          }
          const dialog = new frappe.ui.Dialog({title:__('GOAL fixture preview'), size:'large',
            fields:[{fieldname:'report', fieldtype:'Long Text', label:__('Results'), read_only:1}]});
          dialog.show(); dialog.set_value('report', lines.join('\n'));
        }});
    });
  }
});
