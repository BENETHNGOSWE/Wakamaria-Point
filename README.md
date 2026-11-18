# Wakamaria

Football prediction and final-results website for Frappe / ERPNext v16. The approved standalone prototype remains separate; this app reads real records and does not ship example results.

> Status: initial implementation. This is an experimental staging snapshot, not a production release. Automated tests and an isolated Frappe 16.32.0 / ERPNext 16.33.0 integration test passed with constructed GOAL-shaped responses for five matches. No authenticated live GOAL call or scheduled worker execution was tested by the developer. GOAL score-field semantics need provider confirmation. See TEST_REPORT.md.

## What is included

- `/wakamaria`: responsive public website, grouped by league, filtering/search, Win/Lose/Pending, details and recent history where available. A built-in league image is used when no public league image is supplied.
- Restricted Frappe Desk DocTypes: Wakamaria League, Wakamaria Match, Wakamaria Settings, Wakamaria Screenshot. Only System Manager has access by default. Public endpoints return only published matches in enabled leagues and a limited set of fields.
- Manual prediction entry, optional fixture association via football-data.org, and hourly final-score checking. The API token remains server-side in Frappe's password storage.
- Last three available completed games per team prior to the selected match, from a limited football-data.org background cache. GOAL-only links do not populate team history. Coverage and sufficient history depend on the API plan. Cache warmup can take multiple hours.
- Optional Tesseract OCR for privately uploaded screenshots. A layout-specific card detector proposes editable review rows. Users must review every field and explicitly import selected rows as **unpublished drafts**. Fixture linking and publishing remain manual; no prediction or result is automatically trusted from OCR.
- No betting, odds, payments, user betting accounts or live scores.

## Requirements

- Existing working Frappe v16 / ERPNext v16 bench with scheduler, workers, Redis and database. Back up your site before installing.
- A football-data.org API key and a plan that covers the competitions/current season being used. Free coverage and limits can change; check provider terms, especially before commercial use.
- Optional: `tesseract` binary and Pillow Python package in the Frappe web environment for screenshot OCR. Images are preprocessed locally; OCR text is still imperfect and requires review.
- The server must have network access to `https://api.football-data.org`.

## Install on an existing bench

From the bench directory, after the app has been pushed to the repository:

```bash
bench get-app wakamaria https://github.com/BENETHNGOSWE/Wakamaria-Point.git
bench --site YOUR_SITE install-app wakamaria
bench --site YOUR_SITE migrate
bench --site YOUR_SITE enable-scheduler
bench build --app wakamaria
```

If testing this source without GitHub, copy the folder to `apps/wakamaria`, install it into the bench environment using `bench setup requirements` (or the bench's usual local-app workflow), then run install-app, migrate and build. Exact bench setup varies by deployment. Start the web and background workers using your deployment's process manager.

The public page is `/wakamaria`. To make it the home page, configure the site's home page/landing route in Frappe Website Settings after verifying it does not conflict with an existing ERPNext website. Set the Frappe **system timezone** as appropriate, e.g. `Africa/Dar_es_Salaam`.

## Configure

1. Log in as System Manager. In Desk search for **Wakamaria Settings**, enter the football-data.org API key and enable automatic result checking. Optionally enable recent team history.
2. Six editable leagues are seeded at install. Verify their provider competition codes and free-tier coverage. Add other leagues yourself. Add a public image in **Wakamaria League** if desired; otherwise the default emblem is used. Images on private URLs cannot be shown to anonymous visitors.
3. Create a **Wakamaria Match**: select league, enter the approximate kickoff (in site timezone), and select a prediction. Click **Find provider fixture**, carefully select the exact fixture and save. This fills the provider's fixture and team IDs and precise kickoff. Review the teams before publishing.
4. Check **Published** and save. The match appears publicly. Repeat for other predictions.
5. Hourly jobs check matched fixtures from kickoff until 14 days after kickoff, including recently finished matches so result corrections are picked up. A missing fixture, unavailable API, ambiguous score, non-FINISHED status, or unsupported league does not produce a Win/Lose. For postponed matches outside the 14-day window, update the kickoff or review manually.
6. For manual results, enter both 90-minute scores and check **Result Confirmed**. An enabled provider sync for a matched fixture can later replace/unconfirm these values; leave a fixture unlinked if it must remain manual.
7. To use screenshot OCR, create a **Wakamaria Screenshot**, upload an image **as private** and save. Click **Prepare match review**. The card detector targets the reference app's light-grey league headers and supports up to 8 cards per screenshot; incompatible layouts cannot be detected. Expand each review row and manually check and complete the league, teams, exact kickoff and tip. OCR suggestions can be wrong; the match date alone does not determine kickoff. Use **Select complete rows** to mark all complete unimported rows in the current screenshot, or highlight rows with the far-left grid checkboxes and use **Mark highlighted rows for import**. Save, then click **Create draft matches**. A complete row is not necessarily correct: every OCR suggestion still requires review. The **Refresh suggestions** button re-parses saved OCR and fills empty fields only, without replacing reviewed values. Suggestions may include imperfect team-name fragments. Only unpublished drafts are created; for each draft manually link the exact provider fixture and publish. Already-imported rows are marked; duplicates are blocked where the same team names, league, and kickoff exist. For unsupported layouts add rows manually or use **Extract text with OCR** for raw text. The optional model directory in Wakamaria Settings must contain `eng.traineddata`; blank uses the system model. PNG/JPG/WebP up to 8 MB; Tesseract must be installed. Ensure you have permission to use and republish source predictions.

The sync retrieves matched IDs in batches, handles up to four uncached team histories per run and spaces calls to reduce provider throttling. Manual fixture lookup and other applications sharing the same key can still exceed the provider's limits. The page will show no recent history until the cache is populated; only data available from the plan is used. Scores may be delayed on free plans. Site visitors never receive the API key.

## Settlement rules

All outcomes are based on **90 minutes plus stoppage time**, not extra time or penalties. Supported prediction codes: `1`, `X`, `2`, `1X`, `X2`, `12`, `Over 2.5`, `Under 2.5`, `BTTS Yes`, `BTTS No`. A score is automatically settled only when provider status is `FINISHED` and an unambiguous 90-minute score exists. `AWARDED`, postponed and incomplete matches stay pending. When the source retracts a final result, sync clears the confirmation so an old outcome is not displayed.

Staff should enter predictions before kickoff and preserve records of their publication; this initial version does not provide a tamper-proof prediction audit or lock edits after kickoff. Never present its win rate as guaranteed.

## Tests

```bash
python -m unittest discover -s tests -v
```

For launch, additionally run bench migration and Frappe integration tests with a staging site; test authentication, permissions, scheduler/worker execution, each supported API competition, fixture selection across time zones, result corrections, extra-time fixtures, delayed/postponed matches, screenshot OCR, review table, imports and mobile rendering. API/network and Frappe integration cannot be verified by the standalone unit tests.

## Bulk importing matches using Frappe Data Import

Wakamaria Match and Wakamaria League allow Frappe Data Import for System Manager. Back up before import and test a small file on staging. Create missing league records first. League cells must exactly match existing Wakamaria League record IDs (normally the league name). Use Data Import > Insert New Records, upload XLSX/CSV, inspect the preview and warnings, then start the import. For an official format, download the template from the Data Import tool; select League, Home Team, Away Team, Kickoff (site timezone), Prediction and Published. Blank ID creates a new record. Kickoff is a local site-timezone datetime and supported prediction codes appear under Settlement rules above. Published = 0 keeps a match private; 1 makes it visible immediately. Never invent dates, times, fixture IDs or final scores. Imported match names are not automatically linked by default. Experimental opt-in GOAL fixture matching and final-result checking are described below. Avoid importing the same file twice; standard inserts can create duplicates. Check import logs on partial success before retrying.

## Experimental GOAL API fixture preview (staging only)

Two distinct providers are supported for different purposes. Neither uses OCR to create or change predictions.

**GOAL API preview (not result sync):** Add your key in the GOAL API Key field in Wakamaria Settings and save. Set the GOAL API League ID on each relevant Wakamaria League. For Nations League the provider currently documents `cmr77dw4800fgrx06rwmig2h8`; verify the ID and entitlement on your account. Then select **Preview GOAL fixture matches** in Wakamaria Settings. It reads unlinked, unconfirmed fixtures, groups requests by competition and UTC date, follows pagination, and reports unique candidates only, using exact names plus a narrow Nations League alias for Ireland / Republic of Ireland. The preview does not save links, change results, settle predictions, or enable GOAL API history. Matches with missing league IDs, differing names/times or ambiguous candidates need investigation. League A and B may share the provider competition ID; the correct division and fixtures still need verification. The user reported a successful live preview; an authenticated live sync has not been independently tested by the developer. This diagnostic is limited to 500 rows, 10 groups, 10 pages per group and 12 requests total. It may fail safely if the provider response differs. API usage limits and provider/data rights apply.

**Important:** GOAL API score-field semantics are not officially documented in the sources checked. A separate, experimental opt-in result checker is described below; fixture preview alone never settles predictions. Do not infer that a candidate proves a screenshot's date, competition division, or prediction. Obtain provider confirmation and live test cases including normal time, extra time, penalties, corrections and missing scores before enabling a GOAL result integration. Keep API keys in Frappe Password fields; never paste keys in chat or commit them to Git. The developer has tested a constructed-response sync on Frappe, but not an authenticated live-provider sync or scheduler worker execution.

### Experimental bulk GOAL fixture linking

On a backed-up staging site only, enable **Enable experimental GOAL bulk fixture matching** in Wakamaria Settings after saving the GOAL API key and the correct competition IDs in the league records. An hourly job can link unconfirmed matches, within the last 14 days or next 30 days, where league ID, home and away team names and UTC kickoff are uniquely matched on both sides. Only one explicitly scoped alias is included: Ireland / Republic of Ireland in the UEFA Nations League. Ambiguous matches, those already linked to football-data.org, and manually confirmed matches remain unlinked. The job handles up to five competition/date groups per run in rotation, with at most 12 API requests. With only fixture matching enabled it never changes scores or confirmed results. Existing GOAL links are revalidated on subsequent checks; if a fixture is rescheduled or its identity no longer matches it is not updated. See GOAL Last Sync and GOAL Last Sync Error. Keep workers and scheduler running. API quotas, permissions and coverage apply.

### Experimental GOAL result updates (separate opt-in)

On a backed-up **staging** site only, after fixture matching is working and provider/data-rights checks, enable **Enable experimental GOAL result updates** as well as GOAL bulk fixture matching. This feature is **off by default**. Provider field semantics are based on a third-party analysis of GOAL responses, not official provider confirmation; the five example ordinary-time results were also compared against an independent competition source. This is not evidence that every competition or extra-time case is safe. Do not use for production until the provider confirms the fields and you test the full integration, permissions, scheduler and corrections.

A unique matching league, ordered team IDs, fixture ID and exact kickoff are rechecked on every run. Only status `FINISHED`, at least two hours after kickoff, is considered. Both GOAL FT scores must be nonnegative integers and equal the running-score fields; missing, inconsistent or reset fields, explicit extra-time or penalty fields, non-finished and awarded statuses remain pending. Tests do not prove the provider will always expose extra-time metadata, so extra-time outcomes are not supported or guaranteed. A verified score is used to calculate the supported prediction as Win or Lose. The job rechecks the 14 days after kickoff for corrections; older outcomes are not automatically rechecked. If the provider retracts a score or returns ambiguous data in a complete response, a GOAL-managed outcome returns to Pending. A network outage leaves the last known confirmed outcome unchanged until a successful recheck.

Manually confirmed results and football-data.org linked records are not overwritten. Editing an automatically managed score or result confirmation in Desk transfers ownership to the human; the next GOAL sync will not overwrite that confirmed manual result. Changing the identity or kickoff of a GOAL-linked fixture clears the link and confirmation. The underlying GOAL sync was tested with constructed responses on an isolated Frappe bench, not with a live provider key or scheduler worker. Use a staging site, backups, and verify site time, recent results and correction behaviour. Disable the checkbox to stop future GOAL result changes; this does not automatically undo previously confirmed results.
