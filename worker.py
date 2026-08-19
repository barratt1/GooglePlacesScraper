"""
Job logic: geocode each area, search for the business type, then pull
website/rating/review-count details for every unique business found.

Runs as a background thread inside app.py (no subprocess, no browser —
this is pure HTTP calls to Google's official API, so it's safe to run
on a hosted server like Render).
"""

import csv
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import places_client as pc

FIELDNAMES = [
    "place_id", "name", "address", "phone", "rating", "review_count",
    "has_website", "website", "maps_url", "search_location",
]

ENRICH_WORKERS = 8


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def maps_url_for(place_id):
    return f"https://www.google.com/maps/place/?q=place_id:{place_id}"


class JobState:
    def __init__(self, job_dir):
        self.job_dir = job_dir
        self.status_path = os.path.join(job_dir, "status.json")
        self.data = {
            "phase": "starting",
            "message": "Starting up...",
            "location_index": 0,
            "location_total": 0,
            "current_location": None,
            "candidates_found": 0,
            "enrich_index": 0,
            "enrich_total": 0,
            "matches_found": 0,
            "error": None,
            "updated_at": now_iso(),
        }
        self.write()

    def update(self, **kwargs):
        self.data.update(kwargs)
        self.data["updated_at"] = now_iso()
        self.write()

    def write(self):
        tmp = self.status_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.data, f)
        os.replace(tmp, self.status_path)


def stop_requested(job_dir):
    return os.path.exists(os.path.join(job_dir, "stop.flag"))


def passes_filters(row, job):
    review_count = row.get("review_count") or 0
    try:
        review_count = int(review_count)
    except (TypeError, ValueError):
        review_count = 0
    if review_count < job.get("min_reviews", 0):
        return False

    website_filter = job.get("website_filter", "any")
    has_website = bool(row.get("website"))
    if website_filter == "no_website" and has_website:
        return False
    if website_filter == "has_website" and not has_website:
        return False

    return True


def phase_search(job, job_dir, state, api_key):
    locations = job["locations"]
    state.update(phase="searching", location_total=len(locations))

    candidates = {}
    for i, location in enumerate(locations):
        state.update(
            location_index=i + 1,
            current_location=location,
            message=f"Searching '{job['search_term']}' near {location}...",
        )

        if stop_requested(job_dir):
            state.update(phase="stopped", message="Stopped by user.")
            return None

        try:
            latlng = pc.geocode_area(location, api_key=api_key)
        except pc.PlacesAPIError as e:
            state.update(phase="error", error=str(e), message=str(e))
            return None

        if not latlng:
            state.update(message=f"No location found for '{location}', skipping.")
            continue

        lat, lng = latlng
        try:
            results = pc.text_search(
                job["search_term"], lat, lng,
                radius_meters=job.get("radius_meters", 24000),
                api_key=api_key,
            )
        except pc.PlacesAPIError as e:
            state.update(phase="error", error=str(e), message=str(e))
            return None

        for r in results:
            if r["id"] not in candidates:
                candidates[r["id"]] = {"name": r["name"], "address": r["address"], "search_location": location}

        state.update(candidates_found=len(candidates))
        time.sleep(0.2)

    return candidates


def phase_enrich(job, job_dir, state, api_key, candidates):
    leads_path = os.path.join(job_dir, "leads.csv")
    filtered_path = os.path.join(job_dir, "leads_filtered.csv")

    write_leads_header = not os.path.exists(leads_path)
    leads_file = open(leads_path, "a", newline="", encoding="utf-8")
    leads_writer = csv.DictWriter(leads_file, fieldnames=FIELDNAMES)
    if write_leads_header:
        leads_writer.writeheader()

    write_filtered_header = not os.path.exists(filtered_path)
    filtered_file = open(filtered_path, "a", newline="", encoding="utf-8")
    filtered_writer = csv.DictWriter(filtered_file, fieldnames=FIELDNAMES)
    if write_filtered_header:
        filtered_writer.writeheader()

    state.update(phase="enriching", enrich_total=len(candidates), enrich_index=0, matches_found=0)

    lock = threading.Lock()
    counters = {"done": 0, "matches": 0}
    stopped = {"flag": False}

    def process(place_id, meta):
        if stopped["flag"] or stop_requested(job_dir):
            stopped["flag"] = True
            return
        try:
            details = pc.place_details(place_id, api_key=api_key)
        except pc.PlacesAPIError:
            details = {"name": meta["name"], "address": meta["address"], "phone": None,
                       "rating": None, "review_count": 0, "website": None}

        row = {
            "place_id": place_id,
            "name": details.get("name") or meta["name"],
            "address": details.get("address") or meta["address"],
            "phone": details.get("phone"),
            "rating": details.get("rating"),
            "review_count": details.get("review_count") or 0,
            "has_website": bool(details.get("website")),
            "website": details.get("website"),
            "maps_url": maps_url_for(place_id),
            "search_location": meta["search_location"],
        }

        with lock:
            leads_writer.writerow(row)
            leads_file.flush()
            counters["done"] += 1
            if passes_filters(row, job):
                filtered_writer.writerow(row)
                filtered_file.flush()
                counters["matches"] += 1
            state.update(
                enrich_index=counters["done"],
                matches_found=counters["matches"],
                message=f"Checked: {row['name']}",
            )

    with ThreadPoolExecutor(max_workers=ENRICH_WORKERS) as ex:
        futures = [ex.submit(process, pid, meta) for pid, meta in candidates.items()]
        for _ in as_completed(futures):
            pass

    leads_file.close()
    filtered_file.close()
    return not stopped["flag"]


def run_job(job_dir):
    state = JobState(job_dir)
    try:
        with open(os.path.join(job_dir, "job.json")) as f:
            job = json.load(f)

        api_key = pc.get_api_key()

        candidates = phase_search(job, job_dir, state, api_key)
        if candidates is None:
            return  # stopped or errored already, state already set
        if not candidates:
            state.update(phase="done", message="No businesses found for that search.")
            return

        if stop_requested(job_dir):
            state.update(phase="stopped", message="Stopped by user.")
            return

        ok = phase_enrich(job, job_dir, state, api_key, candidates)
        if ok:
            state.update(phase="done", message="Finished.")
        else:
            state.update(phase="stopped", message="Stopped by user.")

    except pc.PlacesAPIError as e:
        state.update(phase="error", error=str(e), message=str(e))
    except Exception as e:  # noqa: BLE001 - surface any unexpected failure to the UI
        state.update(phase="error", error=str(e), message=f"Unexpected error: {e}")
