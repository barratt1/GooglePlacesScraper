"""
Thin wrapper around Google's official Places API (New) and Geocoding API.

No scraping, no browser automation — this only ever talks to
places.googleapis.com and maps.googleapis.com over normal HTTPS requests,
using an API key you create in Google Cloud Console (see README.md).
"""

import os
import time

import requests

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
DETAILS_URL_TMPL = "https://places.googleapis.com/v1/places/{place_id}"


class PlacesAPIError(Exception):
    pass


def get_api_key():
    key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not key:
        raise PlacesAPIError(
            "GOOGLE_MAPS_API_KEY environment variable is not set. "
            "See README.md for how to create one."
        )
    return key


def geocode_area(area, api_key=None, session=None):
    """Turn a zip code / city / 'City, ST' into (lat, lng), or None if not found."""
    api_key = api_key or get_api_key()
    session = session or requests
    resp = session.get(
        GEOCODE_URL, params={"address": area, "key": api_key}, timeout=15
    )
    if resp.status_code != 200:
        raise PlacesAPIError(f"Geocoding failed ({resp.status_code}): {resp.text[:300]}")
    data = resp.json()
    status = data.get("status")
    if status == "REQUEST_DENIED":
        raise PlacesAPIError(
            "Geocoding request denied — check that the Geocoding API is enabled "
            f"and billing is set up for your project. Google said: {data.get('error_message', '')}"
        )
    if status != "OK" or not data.get("results"):
        return None
    loc = data["results"][0]["geometry"]["location"]
    return loc["lat"], loc["lng"]


def text_search(query, lat, lng, radius_meters=24000, api_key=None, session=None, max_pages=3):
    """Return [{'id', 'name', 'address'}, ...] for a text query biased near (lat, lng)."""
    api_key = api_key or get_api_key()
    session = session or requests
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,nextPageToken",
    }

    # Google requires every paginated request to repeat the exact same
    # search parameters as the first request — only pageToken changes.
    base_body = {
        "textQuery": query,
        "pageSize": 20,
        "locationBias": {
            "circle": {"center": {"latitude": lat, "longitude": lng}, "radius": radius_meters}
        },
    }

    results = []
    page_token = None
    for _ in range(max_pages):
        body = dict(base_body)
        if page_token:
            body["pageToken"] = page_token

        resp = session.post(TEXT_SEARCH_URL, json=body, headers=headers, timeout=20)
        if resp.status_code == 403:
            raise PlacesAPIError(
                "Text Search request denied (403) — check that Places API (New) is "
                f"enabled and billing is set up for your project. Google said: {resp.text[:300]}"
            )
        if resp.status_code != 200:
            raise PlacesAPIError(f"Text Search failed ({resp.status_code}): {resp.text[:300]}")

        data = resp.json()
        for p in data.get("places", []):
            pid = p.get("id")
            if not pid:
                continue
            results.append({
                "id": pid,
                "name": (p.get("displayName") or {}).get("text", ""),
                "address": p.get("formattedAddress", ""),
            })

        page_token = data.get("nextPageToken")
        if not page_token:
            break
        # Google requires a short delay before a fresh pageToken becomes valid.
        time.sleep(2)

    return results


def place_details(place_id, api_key=None, session=None):
    """Return website / rating / review count / phone for one place."""
    api_key = api_key or get_api_key()
    session = session or requests
    headers = {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": (
            "id,displayName,formattedAddress,nationalPhoneNumber,"
            "rating,userRatingCount,websiteUri"
        ),
    }
    resp = session.get(DETAILS_URL_TMPL.format(place_id=place_id), headers=headers, timeout=20)
    if resp.status_code == 403:
        raise PlacesAPIError(
            "Place Details request denied (403) — check that Places API (New) is "
            f"enabled and billing is set up for your project. Google said: {resp.text[:300]}"
        )
    if resp.status_code != 200:
        raise PlacesAPIError(f"Place Details failed ({resp.status_code}): {resp.text[:300]}")

    data = resp.json()
    return {
        "id": data.get("id"),
        "name": (data.get("displayName") or {}).get("text", ""),
        "address": data.get("formattedAddress", ""),
        "phone": data.get("nationalPhoneNumber"),
        "rating": data.get("rating"),
        "review_count": data.get("userRatingCount", 0),
        "website": data.get("websiteUri"),
    }
