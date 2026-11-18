app_name = "wakamaria"
app_title = "Wakamaria"
app_publisher = "Wakamaria"
app_description = "Football predictions and final results"
app_email = "admin@example.com"
app_license = "MIT"
required_apps = ["erpnext"]

# Use /wakamaria by default; set the site's home page in Website Settings if desired.
doctype_js = {
    "Wakamaria Match": "public/js/wakamaria_match.js",
    "Wakamaria Settings": "public/js/wakamaria_settings.js",
    "Wakamaria Screenshot": "public/js/wakamaria_screenshot.js",
}
scheduler_events = {"hourly": ["wakamaria.sync.sync_all", "wakamaria.goal_sync.sync_all"]}
after_install = "wakamaria.setup.after_install"
