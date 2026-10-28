"""Straight-line continuity: hold a geocode that lands off the chain."""

from __future__ import annotations

from trip.continuity import confirmation_text, distance_km, mark_discontinuities


def _pin(name: str, lat: float, lon: float, day: int | None = None, **extra: object) -> dict:
    place = {
        "name": name,
        "role": "waypoint",
        "day": day,
        "found": True,
        "lat": lat,
        "lon": lon,
        "display_name": f"{name}, France",
    }
    place.update(extra)
    return place


def test_paris_lyon_distance_is_a_long_day() -> None:
    km = distance_km(48.8566, 2.3522, 45.7640, 4.8357)
    assert 370 <= km <= 420


def test_short_chain_is_mapped() -> None:
    places = mark_discontinuities(
        [
            _pin("Gap", 45.0, 6.0, 1),
            _pin("Serres", 44.9, 6.1, 2),
            _pin("Avignon", 45.0, 6.4, 3),
        ]
    )
    assert all("needs_confirmation" not in place for place in places)


def test_middle_homonym_is_held() -> None:
    places = mark_discontinuities(
        [
            _pin("Gap", 45.0, 6.0, 1),
            _pin("Orange", 48.5, 6.2, 2),
            _pin("Avignon", 45.0, 6.5, 3),
        ]
    )
    gap, orange, avignon = places
    assert "needs_confirmation" not in gap
    assert "needs_confirmation" not in avignon
    assert orange["needs_confirmation"] is True
    assert orange["nearby"][0]["name"] == "Gap"
    assert orange["nearby"][1]["name"] == "Avignon"
    assert orange["nearby"][0]["km"] > 120
    assert orange["nearby"][1]["km"] > 120
    assert orange["chain_km"] <= 120
    text = confirmation_text(orange)
    assert 'geocoded to "Orange, France"' in text
    assert "clearer name" in text
    assert "confirmed set to true" in text


def test_long_colinear_chain_is_not_held() -> None:
    # About 200 km between each pair, and about 400 km end to end: long days,
    # but each stop lies on the chain.
    places = mark_discontinuities(
        [
            _pin("Paris", 45.0, 0.0, 1),
            _pin("Lyon", 45.0, 2.54, 2),
            _pin("Marseille", 45.0, 5.08, 3),
        ]
    )
    assert all("needs_confirmation" not in place for place in places)


def test_days_stretch_the_budget_for_a_long_but_continuous_chain() -> None:
    places = mark_discontinuities(
        [
            _pin("Paris", 45.0, 0.0, 1),
            _pin("Lyon", 45.0, 2.54, 3),
            _pin("Marseille", 45.0, 5.08, 5),
        ]
    )
    assert all("needs_confirmation" not in place for place in places)


def test_confirmed_homonym_stays_on_the_map() -> None:
    places = mark_discontinuities(
        [
            _pin("Gap", 45.0, 6.0, 1),
            _pin("Orange", 48.5, 6.2, 2, confirmed=True),
            _pin("Avignon", 45.0, 6.5, 3),
        ]
    )
    assert places[1]["confirmed"] is True
    assert "needs_confirmation" not in places[1]


def test_missing_place_is_not_a_neighbour() -> None:
    places = mark_discontinuities(
        [
            _pin("Gap", 45.0, 6.0, 1),
            {"name": "pqris", "role": "waypoint", "day": 2, "found": False},
            _pin("Orange", 48.5, 6.2, 3),
            _pin("Avignon", 45.0, 6.5, 4),
        ]
    )
    assert places[1]["found"] is False
    assert "needs_confirmation" not in places[1]
    assert places[2]["needs_confirmation"] is True


def test_two_stops_are_not_judged() -> None:
    places = mark_discontinuities(
        [
            _pin("Paris", 48.86, 2.35, 1),
            _pin("Nice", 43.70, 7.26, 2),
        ]
    )
    assert all("needs_confirmation" not in place for place in places)


def test_endpoint_far_from_a_tight_chain_is_held() -> None:
    places = mark_discontinuities(
        [
            _pin("Orange", 50.0, 2.0, 1),
            _pin("Gap", 45.0, 6.0, 2),
            _pin("Avignon", 45.05, 6.05, 3),
        ]
    )
    assert places[0]["needs_confirmation"] is True
    assert places[0]["nearby"] == [{"name": "Gap", "km": places[0]["nearby"][0]["km"]}]
    assert places[0]["nearby"][0]["km"] > 120
    assert places[0]["chain_km"] < 40
    assert "needs_confirmation" not in places[1]
    assert "needs_confirmation" not in places[2]
    assert "other stops span" in confirmation_text(places[0])


def test_long_first_leg_of_a_long_trip_is_not_held() -> None:
    places = mark_discontinuities(
        [
            _pin("Paris", 48.8566, 2.3522, 1),
            _pin("Lyon", 45.7640, 4.8357, 2),
            _pin("Marseille", 43.2965, 5.3698, 3),
        ]
    )
    assert all("needs_confirmation" not in place for place in places)
