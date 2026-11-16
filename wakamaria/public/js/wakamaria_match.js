frappe.ui.form.on('Wakamaria Match', {
  refresh(frm) {
    frm.add_custom_button(__('Find provider fixture'), () => {
      if (!frm.doc.league || !frm.doc.kickoff) { frappe.msgprint(__('Enter league and kickoff first.')); return; }
      frappe.call({method:'wakamaria.provider.fixture_candidates', args:{league:frm.doc.league, kickoff:frm.doc.kickoff}, freeze:true, callback(r) {
        const items = r.message || [];
        if (!items.length) { frappe.msgprint(__('No fixtures found for this league and date.')); return; }
        const labels = items.map(x => `${x.id}: ${x.home} vs ${x.away} — ${x.kickoff}`);
        let dialog = new frappe.ui.Dialog({title:__('Confirm provider fixture'), fields:[{fieldname:'fixture',label:__('Select the exact match'),fieldtype:'Select',options:labels.join('\n'),reqd:1}], primary_action_label:__('Use fixture'), primary_action(values) {
          const item=items[labels.indexOf(values.fixture)]; if(!item) return;
          frm.set_value({provider_match_id:item.id,provider_home_team_id:item.home_id,provider_away_team_id:item.away_id,home_team:item.home,away_team:item.away,kickoff:item.kickoff});
          dialog.hide(); frappe.show_alert(__('Fixture selected. Save the match to keep it.'));
        }}); dialog.show();
      }});
    });
  }
});
