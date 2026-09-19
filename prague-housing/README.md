# Prague housing watch

Periodic personal watcher for **new Prague flats and houses** that match a price band and a minimum size, then scores each listing by **public-transport duration** to your places and **how often those lines actually run**.

This is the practical way to go about it: do not scrape every portal into a spreadsheet by hand. Split the job into four stages that you can run on a timer.

```
portals  →  normalize + filter  →  SQLite “have I seen this?”  →  transit score  →  report
```

## How to think about the problem

**1. Treat listings as a feed of new IDs, not a full market dump.**  
Sreality, Bezrealitky, Ulovdomov and the rest recycle the same ads. The useful event is “this `source:id` was not in my database yesterday.” First run can either report everything that matches, or only mark IDs as seen and wait. After that, a hourly/daily job only scores fresh ads.

**2. Filter as close to the source as you can.**  
Price and usable area belong in the search query (Sreality: `czk_price_from` / `czk_price_to`, `usable_area=50|10000`, `locality_region_id=10` for Prague). Re-check locally anyway — portals are sloppy, and a file/CSV drop from another site will not have been pre-filtered.

**3. Split transit into two questions.**  
Door-to-door time (“27 minutes to Anděl if I must be there at 09:00”) needs a **journey planner**. How often the useful line comes (“metro A every 3 min” vs “bus 162 every 20 min”) needs **timetable frequency**. Google Directions sometimes returns both (`transit_details.headway`). PID/Golemio departure boards fill in the period even when the planner does not.

**4. Prefer official or same-as-frontend JSON, and stay polite.**  
Sreality’s site is a SPA over `https://www.sreality.cz/api/cs/v2/estates`. PID publishes GTFS and a stop register; Golemio exposes live departure boards with a free token. Rate-limit, identify the client, keep this personal, and read each site’s terms before you turn the interval down.

**5. Add sources as adapters, not one mega-scraper.**  
Every portal has a different shape. Normalize to one `Listing` (`source`, `source_id`, price, m², GPS, URL). This repo ships Sreality plus a JSON/CSV drop folder. Bezrealitky, Reality.iDNES, Ulovdomov, Facebook groups can be another collector later — or an export you drop into `extra-listings.json`.

## What this tool does

On each `run`:

1. Collect Prague flats/houses from enabled sources.
2. Keep rows that match `deal`, type, price, and `min_area_m2`.
3. Insert into SQLite. Score only **new** keys (or every match on the first run).
4. Find nearby PID stops (walk radius) and, with a Golemio key, compute **headway** from the next departures.
5. If a Google Maps key or OpenTripPlanner URL is set, plan transit to each destination at `arrive_by`.
6. Copy missing line periods from the departure boards onto the itinerary legs.
7. Write a Markdown report that **highlights frequent service** (≤6 min), and optionally Telegram you.

Frequency classes:

| Class | Headway | Meaning |
|---|---|---|
| **frequent** | ≤ 6 min | You can walk up and go (typical metro / busy tram) |
| **regular** | ≤ 12 min | Fine if you glance at the board |
| **sparse** | > 12 min | The period itself is the risk — miss it and the commute blows up |

## Setup

```bash
cd prague-housing
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
prague-housing init --dest config.yaml
```

Edit `config.yaml`:

- `filters.deal`: `rent` or `sale`
- `filters.price_*` and `min_area_m2`
- `destinations`: GPS of work / family / whatever, plus `arrive_by` and `max_duration_min`
- API keys via env vars (`GOOGLE_MAPS_API_KEY`, `GOLEMIO_API_KEY`, `OTP_BASE_URL`, Telegram)

```bash
export GOLEMIO_API_KEY=...          # free: https://api.golemio.cz/api-keys
export GOOGLE_MAPS_API_KEY=...      # Directions API, transit mode
prague-housing run --config config.yaml --report-dir reports
```

Without a journey planner you still get **nearby stops and how often they run**. That is already enough to kill listings that are “only a night bus and a 15-minute walk.”

### Cron (recommended)

```
# every hour, Prague morning included
12 * * * * cd /path/to/prague-housing && .venv/bin/prague-housing run --config config.yaml --report-dir reports
```

Or leave a process running:

```bash
prague-housing watch --config config.yaml
```

`watch` is fine on a home server. Cron is better on a VPS that may restart.

## Sources

| Source | How | Notes |
|---|---|---|
| **Sreality** | Public search JSON the website uses | Prague region `10`, flats + houses, sale or rent. Pagination stops when listing IDs repeat. |
| **File / CSV** | `extra-listings.json` or `.csv` | Use this for Bezrealitky exports, saved searches, or a second collector you write. |
| Next adapters | Same `Listing` shape | Add a module under `prague_housing/collectors/` and register it in `Pipeline._default_collectors`. |

Example file payload: [`extra-listings.example.json`](extra-listings.example.json).

Sreality is the largest Czech board and is enough to validate the loop. Do not HTML-scrape or bypass bot checks — if the JSON endpoint moves, update the collector.

## Transit stack (pick what you want to host)

**Duration (pick one)**

- **Google Directions** `mode=transit` + `arrival_time` — minutes of setup, paid after the free quota, good Prague coverage, sometimes includes `headway`.
- **OpenTripPlanner 2** loaded with [PID GTFS](https://pid.cz/en/opendata/) (`http://data.pid.cz/PID_GTFS.zip`) plus an OSM extract of Prague — self-hosted, no per-request fee, best long-term if you score many ads.
- IDOS has no general public API. Do not scrape it.

**Period / frequency (this is the highlight you asked for)**

- **Golemio** `GET /v2/pid/departureboards?ids=U…` — next departures per line; we take the **median gap**.
- **PID stop register** `https://data.pid.cz/stops/json/stops.json` — keyless, cached daily, used to find stops near the listing GPS.
- Full GTFS `frequencies.txt` / stop_times is the offline version of the same idea if you later run OTP or a local Raptor.

The scorer **merges** them: planner says “take A then 9”; Golemio says “A every 3 min, 9 every 8 min”; the report prints `A (every 3 min) → 9 (every 8 min)` and marks the worst leg (`sparse` wins).

## Config sketch

See [`config.example.yaml`](config.example.yaml). The important bits:

```yaml
filters:
  deal: rent
  property_types: [flat, house]
  price_min_czk: 18000
  price_max_czk: 35000
  min_area_m2: 50
  first_run: report_all   # or mark_seen_only

destinations:
  - id: andel
    name: Anděl
    lat: 50.0714
    lon: 14.4036
    arrive_by: "09:00"
    max_duration_min: 40
```

`first_run: mark_seen_only` is what you want if you turn this on against a hot rental market and do not want a 200-ad dump in Telegram.

## Tests

```bash
cd prague-housing && pip install -e ".[dev]" && pytest
```

Collectors and HTTP are injected; the suite does not call live portals.

## Legal / etiquette

Personal use, low volume, identifiable User-Agent, cached PID stops. Check Sreality / other portals’ terms. Do not republish their catalogs. PID open data is CC-BY — mention Pražská integrovaná doprava if you redistribute derived stop facts.
