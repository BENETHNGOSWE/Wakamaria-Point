# Wakamaria — integration test report

This snapshot is for staging and review, not a production release.

## What was tested

- Installed and migrated on an isolated site with Frappe 16.32.0 and ERPNext 16.33.0. The hourly GOAL job was registered in Scheduled Job Type; the scheduler and background worker were not run end-to-end.
- Ran 40 standalone unit tests successfully.
- Ran the GOAL sync function against the real Frappe database with constructed provider-shaped fixture responses, using fixture IDs and results for the five sample matches. This is a mock of the provider HTTP call, not an authenticated live API test.
- Verified exact links, score/outcome calculation, public match-list API, provider correction, human override, withdrawal on incomplete data, preservation of last confirmed result during an error, and clearing a link after fixture identity editing.
- Checked anonymous HTTP requests cannot access GOAL preview or Wakamaria Settings (HTTP 403).
- Tested the public page in Chromium at 1280 and 375 pixels: five rows, search, details modal, finished filter, and visible Win/Lose badges. Fixed an issue hiding the badge text at smaller widths. No JavaScript errors were observed in these flows.

## Not tested / known limitations

- The test environment did not possess the GOAL key. It did not authenticate to the real provider or exercise GOAL quotas, live payload variations, the queued hourly worker, or the user's existing WSL bench. A previous successful preview by the user is evidence for their preview, not a complete live-result integration test.
- GOAL FT-score semantics have not been officially confirmed. Extra-time and penalty metadata can be absent; automatic 90-minute settlement cannot be guaranteed for every match. The result feature remains experimental and off by default on new sites.
- GOAL-linked matches do not yet fetch last-three-match history; the existing history integration uses football-data.org-linked team IDs where coverage permits.
- Screenshot OCR is unreliable and requires review; it is not an accurate unattended screenshot-to-Excel solution.
- Browser checks were a limited set of flows, not comprehensive accessibility, security, load, compatibility, or production tests. Frappe Data Import spreadsheets were imported by the user previously, not imported in this integration run.
- Production use requires provider rights/field confirmation, live staging and scheduler checks, backups, and credential rotation after exposure. Never place credentials in source, logs, or chat.
