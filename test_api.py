import geopandas as gpd
import pytest
from shapely.geometry import LineString, Point, Polygon

from tests.helpers import (geodesic_area, geodesic_length, kml_bytes, kml_line, kml_point,
                           kml_polygon, zip_shapefile)

# ~1 km x 1 km square in Surat, India (UTM zone 43N)
SURAT_SQ = [(72.80, 21.17), (72.81, 21.17), (72.81, 21.18), (72.80, 21.18), (72.80, 21.17)]
LINE = [(72.80, 21.17), (72.82, 21.19)]


def upload(client, name, data, ctype="application/octet-stream"):
    return client.post("/api/files/", files={"file": (name, data, ctype)})


def test_kml_end_to_end(client):
    kml = kml_bytes(kml_polygon("plot", SURAT_SQ) + kml_line("road", LINE) + kml_point("pin", 72.8, 21.17))
    r = upload(client, "survey.kml", kml)
    assert r.status_code == 201, r.text
    info = r.json()
    assert info["status"] == "COMPLETED" and info["feature_count"] == 3 and info["crs"] == "EPSG:4326"

    assert client.get(f"/api/files/{info['id']}/").json()["filename"] == "survey.kml"

    m = client.get(f"/api/files/{info['id']}/measurements/").json()
    by_type = {x["geometry_type"]: x for x in m["measurements"]}

    # Matches an independent geodesic calculation to well within 0.1 %
    expected_area = geodesic_area(Polygon(SURAT_SQ))
    assert by_type["Polygon"]["area_sq_m"] == pytest.approx(expected_area, rel=1e-3)
    assert by_type["Polygon"]["projected_crs"] == "EPSG:32643"
    assert by_type["LineString"]["length_m"] == pytest.approx(geodesic_length(LineString(LINE)), rel=1e-3)
    assert by_type["Point"]["status"] == "NOT_REQUIRED"
    assert m["summary"]["measured"] == 2 and m["summary"]["not_required"] == 1

    f = client.get(f"/api/files/{info['id']}/features/").json()
    assert f["total"] == 3
    assert {x["properties"]["Name"] for x in f["features"]} == {"plot", "road", "pin"}
    assert all(x["crs"] == "EPSG:4326" and x["geometry"] for x in f["features"])


def test_shapefile_geographic_projected_and_webmercator(client, tmp_path):
    poly = Polygon(SURAT_SQ)
    truth = geodesic_area(poly)
    results = {}
    for epsg in (4326, 32643, 3857):
        gdf = gpd.GeoDataFrame({"name": ["p"]}, geometry=[poly], crs=4326).to_crs(epsg)
        d = tmp_path / str(epsg)
        d.mkdir()
        r = upload(client, "data.zip", zip_shapefile(gdf, d))
        assert r.status_code == 201, r.text
        fid = r.json()["id"]
        assert r.json()["crs"] == f"EPSG:{epsg}"
        results[epsg] = client.get(f"/api/files/{fid}/measurements/").json()["measurements"][0]["area_sq_m"]
    # Same answer whatever CRS the file was stored in (Web Mercator would be ~7 % off if used directly)
    for v in results.values():
        assert v == pytest.approx(truth, rel=1e-3)


def test_southern_hemisphere_zone(client):
    sq = [(151.20, -33.87), (151.21, -33.87), (151.21, -33.86), (151.20, -33.86), (151.20, -33.87)]
    r = upload(client, "syd.kml", kml_bytes(kml_polygon("s", sq)))
    m = client.get(f"/api/files/{r.json()['id']}/measurements/").json()["measurements"][0]
    assert m["projected_crs"] == "EPSG:32756"
    assert m["area_sq_m"] == pytest.approx(geodesic_area(Polygon(sq)), rel=1e-3)


def test_polygon_with_hole_and_multipolygon(client, tmp_path):
    outer = [(72.80, 21.17), (72.81, 21.17), (72.81, 21.18), (72.80, 21.18)]
    hole = [(72.803, 21.173), (72.807, 21.173), (72.807, 21.177), (72.803, 21.177)]
    donut = Polygon(outer, [hole])
    from shapely.geometry import MultiPolygon
    far = Polygon([(72.9, 21.2), (72.91, 21.2), (72.91, 21.21), (72.9, 21.21)])
    gdf = gpd.GeoDataFrame({"n": [1, 2]}, geometry=[donut, MultiPolygon([donut, far])], crs=4326)
    r = upload(client, "d.zip", zip_shapefile(gdf, tmp_path))
    ms = client.get(f"/api/files/{r.json()['id']}/measurements/").json()["measurements"]
    t1 = geodesic_area(Polygon(outer)) - geodesic_area(Polygon(hole))
    assert ms[0]["area_sq_m"] == pytest.approx(t1, rel=1e-3)
    assert ms[1]["area_sq_m"] == pytest.approx(t1 + geodesic_area(far), rel=1e-3)


def test_unsupported_geometries_handled_gracefully(client):
    # KML MultiGeometry mixing a polygon and a point -> GeometryCollection (unsupported, not a crash)
    ring = " ".join(f"{x},{y},0" for x, y in SURAT_SQ)
    multi = ("<Placemark><name>mix</name><MultiGeometry>"
             f"<Polygon><outerBoundaryIs><LinearRing><coordinates>{ring}</coordinates></LinearRing></outerBoundaryIs></Polygon>"
             "<Point><coordinates>72.8,21.17,0</coordinates></Point></MultiGeometry></Placemark>")
    r = upload(client, "mix.kml", kml_bytes(multi + kml_point("pin", 72.8, 21.17)))
    assert r.status_code == 201
    m = client.get(f"/api/files/{r.json()['id']}/measurements/").json()
    kinds = {x["geometry_type"]: x for x in m["measurements"]}
    assert kinds["GeometryCollection"]["status"] == "UNSUPPORTED"
    assert kinds["GeometryCollection"]["area_sq_m"] is None and kinds["GeometryCollection"]["note"]
    assert m["summary"] == {**m["summary"], "unsupported": 1, "not_required": 1, "measured": 0}


def test_measure_unit_edge_cases():
    from pyproj import CRS
    from shapely.geometry import LinearRing, MultiLineString
    from shapely.geometry import Polygon as P

    from app.services.measure import measure
    wgs = CRS.from_epsg(4326)
    assert measure(None, wgs).status == "UNSUPPORTED"
    assert measure(P(), wgs).status == "UNSUPPORTED"
    assert measure(LinearRing(SURAT_SQ), wgs).status == "UNSUPPORTED"
    ml = measure(MultiLineString([LINE, [(72.9, 21.2), (72.91, 21.2)]]), wgs)
    assert ml.status == "MEASURED" and ml.length_m > geodesic_length(LineString(LINE))
    bowtie = measure(P([(72.80, 21.17), (72.81, 21.18), (72.81, 21.17), (72.80, 21.18)]), wgs)
    assert bowtie.status == "MEASURED" and "Invalid" in bowtie.note
    # coordinates outside the valid lat/lon range must not crash
    assert measure(LineString([(0, 95), (1, 96)]), wgs).status == "UNSUPPORTED"


def test_utm_zone_selection():
    from app.services.crs import utm_epsg_for
    assert utm_epsg_for(72.8, 21.17) == 32643
    assert utm_epsg_for(-122.4, 37.8) == 32610
    assert utm_epsg_for(151.2, -33.9) == 32756
    assert utm_epsg_for(180.0, 10) == 32601
    assert utm_epsg_for(0, 89) == 32661 and utm_epsg_for(0, -85) == 32761


def test_missing_prj_fails_clearly(client, tmp_path):
    gdf = gpd.GeoDataFrame({"n": [1]}, geometry=[Polygon(SURAT_SQ)], crs=4326)
    r = upload(client, "noprj.zip", zip_shapefile(gdf, tmp_path, drop_prj=True))
    assert r.status_code == 422
    assert "CRS" in r.json()["detail"]
    fid = r.json()["file"]["id"]
    assert client.get(f"/api/files/{fid}/").json()["status"] == "FAILED"
    assert client.get(f"/api/files/{fid}/measurements/").status_code == 409


def test_pagination(client):
    pls = "".join(kml_point(f"p{i}", 72.8 + i * 0.001, 21.17) for i in range(5))
    fid = upload(client, "pts.kml", kml_bytes(pls)).json()["id"]
    m = client.get(f"/api/files/{fid}/measurements/?limit=2&offset=3").json()
    assert m["total"] == 5 and [x["index"] for x in m["measurements"]] == [3, 4]


@pytest.mark.parametrize("name,data,code", [
    ("notes.txt", b"hello", 415),
    ("empty.kml", b"", 400),
    ("bad.zip", b"not a zip", 422),
    ("bad.kml", b"<kml>broken", 422),
    ("nofiles.zip", b"PK\x05\x06" + b"\x00" * 18, 422),
])
def test_invalid_uploads(client, name, data, code):
    assert upload(client, name, data).status_code == code


def test_not_found(client):
    assert client.get("/api/files/doesnotexist/").status_code == 404
    assert client.get("/api/files/doesnotexist/measurements/").status_code == 404
