# Google Places Lead Finder

A web app for finding businesses by type and area, filtered by review
count and website presence — using Google's official Places API, not
scraping. Because it's a real API call, it can run anywhere, including
a hosted service like Render.

No claimed/unclaimed filter — Google's API doesn't expose that field at
all (confirmed against their current docs), so that filter isn't part of
this version.

---

## Part 1 — Create a Google Places API key

You need a Google Cloud project with billing enabled (Places API requires
a billing account on file even though there's a free monthly allowance —
Google won't charge you unless you go over it).

1. Go to **https://console.cloud.google.com/** and sign in.
2. Top-left, click the project dropdown → **New Project**. Name it
   something like "places-lead-finder" → **Create**. Once created, make
   sure it's selected in the project dropdown.
3. If you haven't linked a billing account to this project yet: go to
   **Billing** in the left sidebar → link or create a billing account and
   attach it to this project. (Required even to stay within the free tier.)
4. Go to **APIs & Services → Library** (left sidebar, or search "API
   Library" in the top search bar).
5. Search for **"Places API (New)"** → click it → **Enable**.
6. Search for **"Geocoding API"** → click it → **Enable**. (This is what
   turns a zip code you type into a map location.)
7. Go to **APIs & Services → Credentials** → **+ Create Credentials** →
   **API key**. Copy the key it generates.
8. Click into the new key to restrict it (recommended, not required):
   under **API restrictions**, choose **Restrict key**, and check only
   **Places API (New)** and **Geocoding API**. Save. This means the key
   is useless for anything else if it ever leaks.

You now have a key that looks like `AIzaSy...`. Keep it private — treat
it like a password, don't commit it to GitHub (the `.gitignore` in this
project already excludes `.env`).

### What this costs

Real numbers as of when this was built (verify current rates at
[Google's pricing page](https://developers.google.com/maps/billing-and-pricing/pricing),
since these do change):

- **Text Search** (finding businesses per area): $32 per 1,000 requests,
  first 5,000/month free.
- **Place Details** (website/rating/reviews per business — this is the
  "Enterprise" tier, since website + rating together require it): roughly
  $17-20 per 1,000 lookups, first 1,000/month free.

For a run covering "hundreds to a thousand" businesses across a
reasonable number of areas, you'll likely stay within the free tier or
land in single-digit dollars. Check your usage anytime under **APIs &
Services → Dashboard** in the console.

---

## Part 2 — Run it locally first

```bash
cd gmaps_places_finder
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

export GOOGLE_MAPS_API_KEY=AIzaSy...your-key-here
python3 app.py
```

Open **http://localhost:5001**, run a small test (one zip code, a handful
of results) to confirm your key works end to end, before doing anything
bigger or deploying it.

---

## Part 3 — Deploy to Render (same pattern as before)

**1. Push this folder to a new GitHub repo.**

```bash
cd gmaps_places_finder
git init
git add .
git commit -m "Initial commit"
```

Then create a new empty repo on github.com (no README/gitignore, since
you already have them), and:

```bash
git remote add origin https://github.com/<your-username>/<repo-name>.git
git branch -M main
git push -u origin main
```

**2. Connect Render to the repo.**

In the Render dashboard: **New +** → **Web Service** → connect the GitHub
repo you just created. Render should auto-detect this as a Python app via
`requirements.txt` and the `Procfile`. If it asks:
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** leave blank (the `Procfile` handles it), or
  `gunicorn app:app --workers 2 --threads 8 --timeout 120` if it asks explicitly.

**3. Set the environment variable.**

In the Render service's **Environment** tab, add:

```
GOOGLE_MAPS_API_KEY = AIzaSy...your-key-here
```

Deploy. Render gives you a public URL (`https://your-app.onrender.com`)
— that's your hosted front end, reachable from anywhere, no Terminal
required.

---

## Notes

- **Free tier hosting note:** Render's free-tier web services spin down
  after inactivity and take ~30-60 seconds to wake back up on the next
  request — the page may look stuck loading briefly the first time you
  visit after it's been idle. A paid Render plan keeps it always-on.
- **Multiple filters:** selecting a website filter narrows results;
  combine with minimum reviews as needed. There's no "OR" logic between
  filters here — just the two independent conditions.
- **Output:** `leads_filtered.csv` (matches your filters) and `leads.csv`
  (everything checked) are downloadable from the page as soon as data
  exists, so you don't need to wait for a full run to finish.
- If Google ever changes API field names or pricing tiers, the two
  places to check are `places_client.py` (the field mask headers) and
  this README's pricing section.
