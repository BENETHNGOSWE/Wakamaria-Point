"""Where a published price comes from.

Two sources, in this order of preference:

  1. **Bookmaker** — a real decimal price quoted by a sportsbook (the-odds-api
     free tier, which aggregates Pinnacle and others). Accurate, but thin
     outside the big leagues and rate-limited.
  2. **Model** — Wakamaria's own estimate from `model.market_odds`, with a
     configurable margin. Available for every fixture on earth, including
     women's and youth games no odds feed covers.

Every price is tagged with which source produced it, and the site shows that
tag. A model estimate is never dressed up as a live market price.
"""

import re
import statistics

import frappe
import requests

from wakamaria import model

ODDS_BASE = "https://api.the-odds-api.com/v4"
ODDS_TIMEOUT = 20
ODDS_CACHE_TTL = 6 * 3600   # free tier is ~8 calls/day; cache hard

# football-data.org competition code -> the-odds-api sport key.
SPORT_KEYS = {
    "PL": "soccer_epl",
    "ELC": "soccer_efl_champ",
    "BL1": "soccer_germany_bundesliga",
    "BL2": "soccer_germany_bundesliga2",
    "SA": "soccer_italy_serie_a",
    "SB": "soccer_italy_serie_b",
    "PD": "soccer_spain_la_liga",
    "SD": "soccer_spain_segunda_division",
    "FL1": "soccer_france_ligue_one",
    "FL2": "soccer_france_ligue_two",
    "DED": "soccer_netherlands_eredivisie",
    "PPL": "soccer_portugal_primeira_liga",
    "CL": "soccer_uefa_champs_league",
    "EL": "soccer_uefa_europa_league",
    "EC": "soccer_uefa_european_championship",
    "WC": "soccer_fifa_world_cup",
    "BSA": "soccer_brazil_campeonato",
    # Codes missing here still work: prices fall back to the model.
    # Add a mapping to use a real bookmaker quote for that competition.
}

# Strip these before comparing team names across two providers.
_NOISE = re.compile(r"\b(fc|cf|afc|sc|ac|as|us|ss|ssc|rc|rcd|cd|club|de|the)\b")


def _normalise(name):
    text = str(name or "").lower()
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return " ".join(_NOISE.sub(" ", text).split())


def _sport_key(provider_code):
    return SPORT_KEYS.get(str(provider_code or "").upper())


def _api_key():
    settings = frappe.get_single("Wakamaria Settings")
    return settings.get_password("odds_api_key", raise_exception=False)


def _events(sport_key):
    """Cached board for one competition, reused for six hours.

    the-odds-api counts one credit per market per region, so h2h+totals in one
    region is 2 credits. The free tier is 500/month — roughly 8 calls a day.
    A long cache is the difference between "usable" and "exhausted by Tuesday".
    """
    cache_key = "wakamaria:odds:" + sport_key
    cached = frappe.cache().get_value(cache_key)
    if cached is not None:
        return cached
    key = _api_key()
    if not key:
        return []
    try:
        response = requests.get(
            f"{ODDS_BASE}/sports/{sport_key}/odds",
            params={"apiKey": key, "regions": "eu",
                    "markets": "h2h,totals", "oddsFormat": "decimal"},
            timeout=ODDS_TIMEOUT,
        )
        response.raise_for_status()
        events = response.json()
    except Exception:
        # Never let a price feed take the prediction run down, and never log the key.
        frappe.log_error(title="Wakamaria odds feed failed",
                         message="the-odds-api request failed. No credentials logged.")
        return []
    events = events if isinstance(events, list) else []
    frappe.cache().set_value(cache_key, events, expires_in_sec=ODDS_CACHE_TTL)
    return events


def _median(values):
    clean = [v for v in values if isinstance(v, (int, float)) and v > 1.0]
    return round(statistics.median(clean), 2) if clean else None


def _market_prices(event):
    """Collapse every bookmaker on an event into one median price per market."""
    collected = {}

    def add(tip, price):
        if isinstance(price, (int, float)) and price > 1.0:
            collected.setdefault(tip, []).append(float(price))

    home = _normalise(event.get("home_team"))
    away = _normalise(event.get("away_team"))

    for bookmaker in event.get("bookmakers") or []:
        for market in bookmaker.get("markets") or []:
            key = market.get("key")
            for outcome in market.get("outcomes") or []:
                name = _normalise(outcome.get("name"))
                price = outcome.get("price")
                point = outcome.get("point")
                if key == "h2h":
                    if name == "draw":
                        add("X", price)
                    elif name == home:
                        add("1", price)
                    elif name == away:
                        add("2", price)
                elif key == "totals" and point is not None:
                    try:
                        point = float(point)
                    except (TypeError, ValueError):
                        continue
                    # Only the lines Wakamaria actually settles are usable.
                    if point == 2.5 and name == "over":
                        add("Over 2.5", price)
                    elif point == 2.5 and name == "under":
                        add("Under 2.5", price)
                    elif point == 3.5 and name == "under":
                        add("Under 3.5", price)
                elif key == "btts":
                    if name == "yes":
                        add("BTTS Yes", price)
                    elif name == "no":
                        add("BTTS No", price)

    return {tip: price for tip, prices in collected.items()
            if (price := _median(prices)) is not None}


def bookmaker_prices(home_team, away_team, provider_code):
    """{tip: price} from the cheapest reliable aggregate for this fixture."""
    sport_key = _sport_key(provider_code)
    if not sport_key:
        return {}
    target_home, target_away = _normalise(home_team), _normalise(away_team)
    for event in _events(sport_key):
        if (_normalise(event.get("home_team")) == target_home
                and _normalise(event.get("away_team")) == target_away):
            return _market_prices(event)
    return {}


def resolve(probabilities, *, home_team, away_team, provider_code, margin=None):
    """{tip: (price, source)} using bookmaker prices where they exist.

    Double-chance markets (1X, X2, 12) are not quoted by most feeds, so they
    fall back to the model even when the 1X2 moneyline is available.
    """
    settings = frappe.get_single("Wakamaria Settings")
    margin = model.DEFAULT_MARGIN if margin is None else margin

    quoted = {}
    if settings.get("odds_api_enabled"):
        try:
            quoted = bookmaker_prices(home_team, away_team, provider_code)
        except Exception:
            quoted = {}

    prices = {}
    for tip, probability in probabilities.items():
        if tip in quoted:
            prices[tip] = (quoted[tip], "Bookmaker")
        else:
            estimate = model.market_odds(probability, margin)
            if estimate:
                prices[tip] = (estimate, "Model")
    return prices
