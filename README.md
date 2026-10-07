# Geospatial File Measurement API

A FastAPI service that accepts a **KML** or a **zipped Shapefile**, extracts every feature
(index, geometry type, geometry, CRS, properties) and returns **area** (polygons) and **length**
(lines), calculated in a projected CRS — never in raw lat/lon degrees.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload                           # http://localhost:8000
```

* Interactive docs: http://localhost:8000/docs
* Tests: `pytest -q`
* Docker: `docker build -t geo-api . && docker run -p 8000:8000 geo-api`
* Config via env vars (prefix `GEO_`): `GEO_DATABASE_URL` (default `sqlite:///./geo.db`),
  `GEO_MAX_UPLOAD_BYTES` (50 MB), `GEO_MAX_UNCOMPRESSED_BYTES`, `GEO_MAX_FEATURES`.

Quick try: `curl -F "file=@samples/surat.kml" http://localhost:8000/api/files/`

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/files/` | Upload `.kml` or `.zip` (Shapefile) as multipart field `file`; processed synchronously |
| GET | `/api/files/{id}/` | File info / status |
| GET | `/api/files/{id}/measurements/` | Per-feature measurements + summary (`limit`, `offset`) |
| GET | `/api/files/{id}/features/` | Extracted features with GeoJSON geometry and properties (`limit`, `offset`) |
| GET | `/api/files/` | List uploaded files |
| DELETE | `/api/files/{id}/` | Delete a file and its features |
| GET | `/health` | Liveness |

### `POST /api/files/` → 201
```json
{"id": "fb1a8e7c...", "filename": "survey.kml", "file_type": "kml",
 "feature_count": 3, "crs": "EPSG:4326", "status": "COMPLETED", "error": null,
 "created_at": "2026-10-07T10:41:42Z"}
```
Errors: `415` wrong extension · `400` empty file · `413` too large ·
`422` file accepted but unreadable (corrupt zip, no `.shp`, missing `.prj`, …). A 422 body contains
`detail` and the stored `file` record (`status: FAILED`), which stays retrievable via `GET`.

### `GET /api/files/{id}/measurements/`
```json
{
  "file_id": "fb1a8e7c...", "total": 3, "limit": 100, "offset": 0,
  "summary": {"total_area_sq_m": 1150362.2276, "total_length_m": 3036.684,
              "measured": 2, "not_required": 1, "unsupported": 0},
  "measurements": [
    {"index": 0, "layer": "surat", "geometry_type": "Polygon", "crs": "EPSG:4326",
     "projected_crs": "EPSG:32643", "status": "MEASURED",
     "area_sq_m": 1150362.2276, "length_m": null, "note": null},
    {"index": 1, "geometry_type": "LineString", "projected_crs": "EPSG:32643",
     "status": "MEASURED", "area_sq_m": null, "length_m": 3036.684, "note": null},
    {"index": 2, "geometry_type": "Point", "projected_crs": null,
     "status": "NOT_REQUIRED", "area_sq_m": null, "length_m": null,
     "note": "No measurement defined for points"}
  ]
}
```
`status` is `MEASURED`, `NOT_REQUIRED` (points) or `UNSUPPORTED` (null/empty geometry,
`GeometryCollection`, `LinearRing`, out-of-range coordinates) — the `note` says why. Requesting
measurements for a `FAILED` file returns `409`; unknown id returns `404`.

### `GET /api/files/{id}/features/`
Each feature: `index`, `layer`, `geometry_type`, `crs`, `geometry` (GeoJSON in the **source** CRS),
`properties`.

## Architecture

```
app/
  main.py            app + lifespan (creates tables)
  config.py          env-driven settings
  db.py, models.py   SQLAlchemy 2.0 (GeoFile, Feature); SQLite by default
  schemas.py         Pydantic response models
  api/files.py       HTTP layer only: validation, streaming upload, pagination
  services/
    reader.py        zip/KML -> RawFeature records (GeoPandas + pyogrio)
    crs.py           UTM selection, cached pyproj transformers
    measure.py       one geometry -> Measurement (never raises)
    processor.py     read -> measure -> persist, sets COMPLETED/FAILED
tests/               end-to-end API tests validated against independent geodesic maths
```

**File-processing flow**: upload is streamed to a temp dir with a size cap → extension decides
`kml` / `shapefile` → Shapefile zips are extracted safely (only `.shp/.shx/.dbf/.prj/.cpg`, names
flattened to prevent zip-slip, uncompressed-size cap against zip bombs) → each KML layer / each `.shp`
is read → features are stored with GeoJSON geometry, properties, CRS → measured → `status=COMPLETED`.
Any failure is caught and stored as `FAILED` with a message.

**Measurement flow** (`measure.py`): null/empty → UNSUPPORTED · Point/MultiPoint → NOT_REQUIRED ·
Polygon/MultiPolygon → area (holes subtracted, parts summed) · LineString/MultiLineString → length ·
anything else → UNSUPPORTED. Z values are dropped; invalid geometries (e.g. bow-ties) are measured
but flagged in `note`.

**CRS handling**: the source CRS is read from the file (KML is always EPSG:4326; Shapefile from `.prj`).
For every feature: reproject to WGS84 → pick the **UTM zone of the feature's representative point**
(`EPSG:326xx` north / `327xx` south; UPS 32661/32761 beyond 84°N / 80°S) → reproject to it → measure
in metres. This is applied uniformly, so files already in a projected CRS (e.g. Web Mercator, whose
areas are inflated ~7% at Surat's latitude) are also normalised. Tests confirm the same polygon
yields the same area from EPSG:4326, 32643 and 3857 inputs, within 0.1% of a geodesic reference.

## Design Decisions

* **FastAPI over Django**: small service, no admin/ORM-GIS need; async-ready, automatic OpenAPI docs,
  Pydantic validation. Endpoints are plain `def` so FastAPI runs the blocking GDAL work in a threadpool.
* **GeoPandas/pyogrio over raw `fiona`/`fastkml`**: one reader for both formats, wheels bundle GDAL
  (no system install), fast vectorised I/O.
* **Per-feature UTM vs one CRS per file**: a file can span several zones; per-feature choice keeps
  distortion tiny. Alternatives considered: a single equal-area CRS (good for area, worse for length),
  and geodesic calculation with `pyproj.Geod` (most accurate, but the brief asks for projected
  measurement; I use Geod only in tests as an independent oracle).
* **Store features in the DB** (GeoJSON in a JSON column) so measurement/feature endpoints are cheap
  and paginated. Alternative: re-read the original file per request (saves space, costs CPU) — or
  PostGIS (best for spatial queries, heavier setup than needed here).
* **Synchronous processing**: simple and deterministic for ≤50 MB files; the `status` field already
  models `PROCESSING/COMPLETED/FAILED`, so moving to a queue doesn't change the API.
* **Missing `.prj` → FAILED** rather than guessing a CRS; a wrong guess silently produces wrong areas.
* **Measurements never crash the upload**: unsupported/odd geometries get a status and note.

## Known limitations
* Features spanning multiple UTM zones (or country-scale polygons) lose accuracy; a geodesic fallback
  would be better there.
* `GeometryCollection`s (KML `MultiGeometry` with mixed types) are reported as UNSUPPORTED.
* KML features with `<gx:Track>`, `NetworkLink`, ground overlays are ignored by GDAL.
* No authentication; uploaded files are not retained after processing.

## Learning & Future Scope
**Learning**: how much silent error comes from CRS assumptions (degrees vs metres, Web Mercator
inflation); GDAL's KML driver behaviour (layers = folders, always 4326, MultiGeometry →
GeometryCollection); defensive zip extraction; designing "partial success" responses instead of
all-or-nothing failures.

**Future scope**: background processing (Celery/RQ) with progress; PostGIS + Alembic migrations;
geodesic fallback for large features; measure GeometryCollection members; GeoJSON/GeoPackage/
KMZ support; export results as CSV/GeoJSON; auth + per-user quotas; retaining originals in S3;
CI (GitHub Actions) with lint and coverage.
