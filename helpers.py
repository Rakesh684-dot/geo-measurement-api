import io
import zipfile
from pathlib import Path

import geopandas as gpd
from pyproj import Geod
from shapely.geometry import LineString, Point, Polygon

GEOD = Geod(ellps="WGS84")


def geodesic_area(poly: Polygon) -> float:
    return abs(GEOD.geometry_area_perimeter(poly)[0])


def geodesic_length(line: LineString) -> float:
    return GEOD.geometry_length(line)


def zip_shapefile(gdf: gpd.GeoDataFrame, tmp_path: Path, drop_prj: bool = False) -> bytes:
    shp = tmp_path / "data.shp"
    gdf.to_file(shp)
    if drop_prj:
        (tmp_path / "data.prj").unlink(missing_ok=True)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for p in tmp_path.glob("data.*"):
            zf.write(p, p.name)
    return buf.getvalue()


def kml_bytes(placemarks: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
        f"{placemarks}</Document></kml>"
    ).encode()


def kml_polygon(name, coords):
    c = " ".join(f"{x},{y},0" for x, y in coords)
    return (f"<Placemark><name>{name}</name><Polygon><outerBoundaryIs><LinearRing>"
            f"<coordinates>{c}</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>")


def kml_line(name, coords):
    c = " ".join(f"{x},{y},0" for x, y in coords)
    return f"<Placemark><name>{name}</name><LineString><coordinates>{c}</coordinates></LineString></Placemark>"


def kml_point(name, x, y):
    return f"<Placemark><name>{name}</name><Point><coordinates>{x},{y},0</coordinates></Point></Placemark>"
