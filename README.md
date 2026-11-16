# Wakamaria

Football prediction and final-results website for Frappe / ERPNext v16. The approved standalone prototype remains separate; this app reads real records and does not ship example results.

> Status: initial implementation. The pure prediction rules have automated tests, but the app has not yet been installed or integration-tested against a running Frappe v16 bench, a real API key, or Tesseract. Test on a staging site before production.

## What is included

- `/wakamaria`: responsive public website, grouped by league, filtering/search, Win/Lose/Pending, details and recent history where available. A built-in league image is used when no public league image is supplied.
- Restricted Frappe Desk DocTypes: Wakamaria League, Wakamaria Match, Wakamaria Settings, Wakamaria Screenshot. Only System Manager has access by default. Public endpoints return only published matches in enabled leagues and a limited set of fields.
- Manual prediction entry, optional fixture association via football-data.org, and hourly final-score checking. The API token remains server-side in Frappe's password storage.
- Last three available completed games per team prior to the selected match, from a limited background cache. Coverage and sufficient history depend on the API plan. Cache warmup can take multiple hours.
- Optional Tesseract OCR for privately uploaded screenshots. **OCR extracts raw text only:** an admin must review it and manually create/publish matches. Automated parsing, fixture matching and prediction creation from screenshots are not implemented yet.
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
7. To use screenshot OCR, create a **Wakamaria Screenshot**, upload an image **as private**, save, then click **Extract text with OCR**. Inspect the text and create matches manually. PNG/JPG/WebP up to 8 MB; Tesseract must be installed. Ensure you have permission to use and republish source predictions.

The sync retrieves matched IDs in batches, handles up to four uncached team histories per run and spaces calls to reduce provider throttling. Manual fixture lookup and other applications sharing the same key can still exceed the provider's limits. The page will show no recent history until the cache is populated; only data available from the plan is used. Scores may be delayed on free plans. Site visitors never receive the API key.

## Settlement rules

All outcomes are based on **90 minutes plus stoppage time**, not extra time or penalties. Supported prediction codes: `1`, `X`, `2`, `1X`, `X2`, `12`, `Over 2.5`, `Under 2.5`, `BTTS Yes`, `BTTS No`. A score is automatically settled only when provider status is `FINISHED` and an unambiguous 90-minute score exists. `AWARDED`, postponed and incomplete matches stay pending. When the source retracts a final result, sync clears the confirmation so an old outcome is not displayed.

Staff should enter predictions before kickoff and preserve records of their publication; this initial version does not provide a tamper-proof prediction audit or lock edits after kickoff. Never present its win rate as guaranteed.

## Tests

```bash
python -m unittest discover -s tests -v
```

For launch, additionally run bench migration and Frappe integration tests with a staging site; test authentication, permissions, scheduler/worker execution, each supported API competition, fixture selection across time zones, result corrections, extra-time fixtures, delayed/postponed matches, OCR and mobile rendering. API/network and Frappe integration cannot be verified by the standalone unit tests.
