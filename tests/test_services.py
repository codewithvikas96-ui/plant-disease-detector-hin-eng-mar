"""Unit tests for the services that do not need the CNN."""

from datetime import datetime, timedelta

from app.ratelimit import RateLimiter
from app.services import advice, outbreaks, weather


# ------------------------------------------------------------------ advice
def test_cost_per_acre_is_dose_times_volume_times_price():
    entry = {
        "healthy": False, "pathogen_type": "fungal", "spray_l_per_acre": 200,
        "treatments": [{"product": "Mancozeb 75% WP", "dose": 2.5, "unit": "g"}],
    }
    plan = advice.plan(entry, "en")
    item = plan["chemical"][0]
    assert item["qty_per_acre"] == 500           # 2.5 g/L x 200 L
    assert item["cost_per_acre"] == 250          # 500 g x Rs 0.5/g
    assert plan["organic"]["items"]              # fungal has organic options


def test_no_plan_for_healthy_leaf():
    assert advice.plan({"healthy": True}, "mr") is None


# ----------------------------------------------------------------- weather
def forecast(hours: int = 72, rain_at: set[int] = frozenset(), humid: bool = False):
    """A synthetic Open-Meteo response starting at 00:00 today."""
    start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    times = [(start + timedelta(hours=i)).isoformat(timespec="minutes") for i in range(hours)]
    return {
        "timezone": "Asia/Kolkata",
        "current": {"time": times[0], "temperature_2m": 24, "relative_humidity_2m": 60,
                    "wind_speed_10m": 5, "precipitation": 0},
        "hourly": {
            "time": times,
            "temperature_2m": [24] * hours,
            "relative_humidity_2m": [95 if humid else 60] * hours,
            "precipitation_probability": [90 if i in rain_at else 0 for i in range(hours)],
            "precipitation": [2.0 if i in rain_at else 0 for i in range(hours)],
            "wind_speed_10m": [5] * hours,
        },
    }


def test_dry_calm_day_gives_daylight_window():
    w = weather.summarise(forecast())
    first = datetime.fromisoformat(w["windows"][0]["start"])
    assert 6 <= first.hour <= 18
    assert w["disease_risk"] == "low"
    assert len(w["hourly"]) == 48


def test_no_window_ends_within_four_hours_of_rain():
    rain = {12}  # noon today
    w = weather.summarise(forecast(rain_at=rain))
    rain_time = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
    for win in w["windows"]:
        start, end = datetime.fromisoformat(win["start"]), datetime.fromisoformat(win["end"])
        if start.date() == rain_time.date():
            assert end < rain_time - timedelta(hours=3) or start > rain_time
    assert w["rain"]["first_rain"].startswith(rain_time.strftime("%Y-%m-%dT12"))


def test_long_humid_spell_is_high_fungal_risk():
    assert weather.summarise(forecast(humid=True))["disease_risk"] == "high"


# --------------------------------------------------------------- outbreaks
def test_location_is_snapped_to_the_grid_cell_centre():
    # Two farms 1 km apart land in the same ~5 km cell.
    assert outbreaks.snap(18.5204) == outbreaks.snap(18.5290) == 18.525


def test_reports_are_counted_per_cell_and_disease(scans_db):
    outbreaks.record("Tomato___Late_blight", 18.52, 73.86, "cnn")
    outbreaks.record("Tomato___Late_blight", 18.53, 73.88, "cnn")
    outbreaks.record("Grape___Black_rot", 20.00, 73.79, "cnn")
    rows = outbreaks.summary(days=7)
    assert {(r["class_name"], r["count"]) for r in rows} == {
        ("Tomato___Late_blight", 2), ("Grape___Black_rot", 1)}


# -------------------------------------------------------------- rate limit
def test_rate_limiter_blocks_after_limit_per_client():
    limiter = RateLimiter(limit=3, window_s=60)
    assert all(limiter.allow("a") for _ in range(3))
    assert not limiter.allow("a")
    assert limiter.allow("b")  # someone else is unaffected
