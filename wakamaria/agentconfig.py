"""Agent settings, resolved. Pure: no Frappe import, so it can be tested.

Frappe does not apply new field defaults to a Single record that already
exists. Adding fields to Wakamaria Settings therefore leaves every new numeric
field at 0 on an existing site, and the form honestly shows 0.00.

Zero is not a meaningful value for any agent setting, so it is read as "unset"
and a sane default is used. Otherwise the agent would happily run with a
0-hour look-ahead, a cap of 0 per run, and a confidence band of 0.00 to 0.00 —
publish nothing, and report success.
"""

from wakamaria import model

DEFAULTS = {
    "horizon_hours": 36,
    "max_per_run": 12,
    "max_per_day": 20,
    "min_confidence": 0.35,
    "max_confidence": 0.97,
    "family_cap": 3,
    "margin": model.DEFAULT_MARGIN,
    "pause_after_losses": 0,
}

# Settings field name -> (config key, cast)
FIELDS = {
    "agent_horizon_hours": ("horizon_hours", int),
    "agent_max_per_run": ("max_per_run", int),
    "agent_max_per_day": ("max_per_day", int),
    "agent_min_confidence": ("min_confidence", float),
    "agent_max_confidence": ("max_confidence", float),
    "agent_family_cap": ("family_cap", int),
    "agent_margin": ("margin", float),
    "agent_pause_after_losses": ("pause_after_losses", int),
}


def resolve(settings):
    """Return every agent setting as a number, defaulting anything unset."""
    config = {}
    for fieldname, (key, cast) in FIELDS.items():
        value = settings.get(fieldname)
        if value in (None, "", 0, 0.0):
            config[key] = DEFAULTS[key]
            continue
        try:
            config[key] = cast(value)
        except (TypeError, ValueError):
            config[key] = DEFAULTS[key]
    return config
