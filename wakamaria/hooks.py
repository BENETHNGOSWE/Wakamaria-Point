app_name = "wakamaria"
app_title = "Wakamaria"
app_publisher = "Wakamaria"
app_description = "Football predictions and final results"
app_email = "hello@wakamaria.co.tz"
app_license = "MIT"
required_apps = ["erpnext"]

# Use /wakamaria by default; set the site's home page in Website Settings if desired.
doctype_js = {
    "Wakamaria Match": "public/js/wakamaria_match.js",
    "Wakamaria Settings": "public/js/wakamaria_settings.js",
    "Wakamaria Screenshot": "public/js/wakamaria_screenshot.js",
}
scheduler_events = {
    "hourly": ["wakamaria.sync.sync_all", "wakamaria.goal_sync.sync_all"],
    # The prediction agent creates the tips; sync_all settles them. Every two
    # hours is enough for a 36h look-ahead and stays inside provider rate limits.
    "cron": {"0 */2 * * *": ["wakamaria.agent.run_agent"]},
}
after_install = "wakamaria.setup.after_install"
