"""Hold back a geocoded stop that lands off an otherwise continuous chain.

This catches a name that resolved to the wrong place: the other stops form
a coherent chain, and this one does not sit on it. A long chain of intended
places is left on the map. This does not judge whether a day is too far for
the rider. A stop the caller has already confirmed is kept.
"""

from __future__ import annotations

import math
from typing import Any

EARTH_RADIUS_KM = 6371.0
# Crow-flies ceiling for one day. A leg under this can still be a hard ride
# on roads; a stop is held back only when it spikes off the chain, not because
# a leg is merely long.
KM_PER_DAY = 120.0
# An endpoint is off the chain when its jump is several times the span of
# every other stop, and those other stops already fit in their day budgets.
ENDPOINT_SPAN_FACTOR = 3.0


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def mark_discontinuities(places: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Copy places, marking stops that geocoded off the chain.

    A marked stop keeps its coordinates and gains needs_confirmation, nearby
    distances, and chain_km. The map should not draw it until the caller
    sends a clearer name or confirmed true.
    """
    marked = [_without_hold(place) for place in places]
    found = [place for place in marked if _is_pin(place)]
    if len(found) < 3:
        return marked

    for index in range(1, len(found) - 1):
        place = found[index]
        if place.get("confirmed") is True:
            continue
        prev = found[index - 1]
        nxt = found[index + 1]
        to_prev = _between(prev, place)
        to_next = _between(place, nxt)
        shortcut = _between(prev, nxt)
        if (
            to_prev > _budget_km(prev, place)
            and to_next > _budget_km(place, nxt)
            and shortcut <= _budget_km(prev, nxt)
        ):
            _hold(
                place,
                nearby=[(prev, to_prev), (nxt, to_next)],
                chain_km=shortcut,
            )

    _hold_endpoint(found[0], found[1:], neighbor=found[1])
    _hold_endpoint(found[-1], found[:-1], neighbor=found[-2])
    return marked


def confirmation_text(place: dict[str, Any]) -> str:
    """Tell the caller how to correct or accept one held stop."""
    shown = place.get("display_name") or place.get("name") or "(empty)"
    nearby = place.get("nearby") or []
    where = " and ".join(
        f"{item['km']} km from {item['name']}" for item in nearby
    )
    sentence = f"Confirm {place.get('name') or '(empty)'} before mapping: it geocoded to \"{shown}\""
    if where:
        sentence += f", {where}"
    chain = place.get("chain_km")
    if chain is not None and len(nearby) >= 2:
        sentence += f", while {nearby[0]['name']} to {nearby[1]['name']} is {chain} km"
    elif chain is not None and len(nearby) == 1:
        sentence += f", while the other stops span {chain} km"
    sentence += (
        ". If you meant a different place, call show_trip_map again with a clearer name. "
        "If this geocoded place is the one you meant, call show_trip_map again "
        "with confirmed set to true on this stop."
    )
    return sentence


def _without_hold(place: dict[str, Any]) -> dict[str, Any]:
    item = dict(place)
    item.pop("needs_confirmation", None)
    item.pop("nearby", None)
    item.pop("chain_km", None)
    return item


def _is_pin(place: dict[str, Any]) -> bool:
    return bool(
        place.get("found") and place.get("lat") is not None and place.get("lon") is not None
    )


def _between(a: dict[str, Any], b: dict[str, Any]) -> float:
    return distance_km(a["lat"], a["lon"], b["lat"], b["lon"])


def _day_number(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def _day_span(a: dict[str, Any], b: dict[str, Any]) -> int:
    left = _day_number(a.get("day"))
    right = _day_number(b.get("day"))
    if left is None or right is None:
        return 1
    return max(1, abs(right - left))


def _budget_km(a: dict[str, Any], b: dict[str, Any]) -> float:
    return KM_PER_DAY * _day_span(a, b)


def _hold(
    place: dict[str, Any],
    *,
    nearby: list[tuple[dict[str, Any], float]],
    chain_km: float,
) -> None:
    place["needs_confirmation"] = True
    place["nearby"] = [
        {"name": other.get("name") or "(empty)", "km": int(round(km))}
        for other, km in nearby
    ]
    place["chain_km"] = int(round(chain_km))


def _hold_endpoint(
    place: dict[str, Any],
    rest: list[dict[str, Any]],
    *,
    neighbor: dict[str, Any],
) -> None:
    if place.get("confirmed") is True or place.get("needs_confirmation"):
        return
    if not rest or not _legs_within_budget(rest):
        return
    jump = _between(place, neighbor)
    span = _diameter_km(rest)
    if jump > _budget_km(place, neighbor) and jump > ENDPOINT_SPAN_FACTOR * span:
        _hold(place, nearby=[(neighbor, jump)], chain_km=span)


def _legs_within_budget(points: list[dict[str, Any]]) -> bool:
    return all(
        _between(a, b) <= _budget_km(a, b) for a, b in zip(points, points[1:])
    )


def _diameter_km(points: list[dict[str, Any]]) -> float:
    diameter = 0.0
    for index, origin in enumerate(points):
        for other in points[index + 1 :]:
            diameter = max(diameter, _between(origin, other))
    return diameter
