import argparse
import logging
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterable, List, Sequence, Tuple

import geopandas as gpd
import numpy as np
import osmnx as ox
import pandas as pd
import rasterio
from pyproj import CRS, Transformer
from rasterio.features import rasterize, shapes
from rasterio.mask import mask
from shapely.geometry import Point, mapping, shape

LOGGER = logging.getLogger("reverse_viewshed")
DEFAULT_BUFFER_METERS = 1000
DEFAULT_TARGET_HEIGHT = 1.6  # average human eye height


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a reverse viewshed raster showing where a POI building is visible "
            "based on OSM building heights and a DEM."
        )
    )
    parser.add_argument(
        "--target",
        action="append",
        metavar="LAT,LON",
        help="Latitude,Longitude pair for a rooftop/observer point (can be repeated).",
    )
    parser.add_argument("--lat", type=float, help="Latitude of the primary target point.")
    parser.add_argument("--lon", type=float, help="Longitude of the primary target point.")
    parser.add_argument(
        "--buffer-m",
        type=int,
        default=DEFAULT_BUFFER_METERS,
        help=f"Buffer radius around the target(s) in meters. Default: {DEFAULT_BUFFER_METERS}.",
    )
    parser.add_argument(
        "--dem",
        type=Path,
        required=True,
        help="Path to a DEM GeoTIFF (e.g., clipped SRTM tile).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("viewshed_output.tif"),
        help="Destination GeoTIFF for the binary viewshed (1=visible, 0=not visible).",
    )
    parser.add_argument(
        "--dsm-output",
        type=Path,
        help="Optional path to store the intermediate DSM (DEM + building heights).",
    )
    parser.add_argument(
        "--vector-output",
        type=Path,
        help="Optional path (e.g., .geojson, .gpkg) to store the visible area polygons.",
    )
    parser.add_argument(
        "--observer-height",
        type=float,
        default=0.0,
        help="Height of the observer above the DSM surface. Default: 0 (rooftop).",
    )
    parser.add_argument(
        "--target-height",
        type=float,
        default=DEFAULT_TARGET_HEIGHT,
        help=f"Height of the observed target above the DSM surface. Default: {DEFAULT_TARGET_HEIGHT} m.",
    )
    parser.add_argument(
        "--max-distance",
        type=float,
        default=None,
        help="Optional maximum distance (meters) for GDAL viewshed. Defaults to buffer radius.",
    )
    parser.add_argument(
        "--gdal-bin",
        type=str,
        default="gdal_viewshed",
        help="Name or absolute path of the GDAL viewshed executable.",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity.",
    )
    return parser.parse_args()


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def parse_target_points(args: argparse.Namespace) -> List[Tuple[float, float]]:
    points: List[Tuple[float, float]] = []
    if args.target:
        for value in args.target:
            try:
                lat_str, lon_str = value.split(",")
                points.append((float(lat_str), float(lon_str)))
            except ValueError as exc:
                raise ValueError(f"Invalid --target value '{value}'. Expected format LAT,LON") from exc
    if not points and args.lat is not None and args.lon is not None:
        points.append((args.lat, args.lon))
    if not points:
        raise ValueError("Provide at least one target point using --target or --lat/--lon.")
    return points


def create_buffer_polygon(points: Sequence[Tuple[float, float]], buffer_m: float):
    gdf = gpd.GeoDataFrame(
        geometry=[Point(lon, lat) for lat, lon in points],
        crs="EPSG:4326",
    )
    utm_crs = gdf.estimate_utm_crs()
    gdf_utm = gdf.to_crs(utm_crs)
    buffered = gdf_utm.buffer(buffer_m).unary_union
    buffered_ll = gpd.GeoSeries([buffered], crs=utm_crs).to_crs("EPSG:4326").iloc[0]
    LOGGER.info("AOI buffer generated using %s", utm_crs)
    return buffered_ll


def fetch_buildings(buffer_geom) -> gpd.GeoDataFrame:
    LOGGER.info("Downloading OSM buildings within AOI…")
    tags = {"building": True}
    if hasattr(ox, "features_from_polygon"):
        buildings = ox.features_from_polygon(buffer_geom, tags)
    else:
        buildings = ox.geometries_from_polygon(buffer_geom, tags)
    buildings = buildings[buildings.geometry.notnull()].copy()
    if buildings.empty:
        raise RuntimeError("No building footprints retrieved from OSM for the AOI.")

    # Normalize heights (meters)
    height = pd.to_numeric(buildings.get("height"), errors="coerce")
    levels = pd.to_numeric(buildings.get("building:levels"), errors="coerce")
    derived = levels * 3.0
    buildings["height_m"] = height.fillna(derived)
    buildings = buildings.dropna(subset=["height_m"])
    if buildings.empty:
        raise RuntimeError("No buildings with usable height information in AOI.")

    LOGGER.info("Retrieved %d buildings with heights.", len(buildings))
    return buildings


def clip_dem_to_aoi(dem_path: Path, buffer_geom):
    with rasterio.open(dem_path) as src:
        LOGGER.info("Clipping DEM (%s) to AOI…", dem_path)
        buffer_proj = gpd.GeoSeries([buffer_geom], crs="EPSG:4326").to_crs(src.crs).iloc[0]
        dem, transform = mask(src, [mapping(buffer_proj)], crop=True)
        profile = src.profile.copy()
        profile.update(
            height=dem.shape[1],
            width=dem.shape[2],
            transform=transform,
            count=1,
            dtype="float32",
        )
        if profile.get("nodata") is None:
            profile["nodata"] = -9999.0
        dem = dem.astype("float32")
        LOGGER.info("DEM clipped: %dx%d pixels", profile["width"], profile["height"])
        return dem[0], profile


def build_dsm(dem_array: np.ndarray, profile: dict, buildings: gpd.GeoDataFrame) -> np.ndarray:
    LOGGER.info("Rasterizing building heights…")
    dem_crs = CRS.from_user_input(profile["crs"])
    buildings_proj = buildings.to_crs(dem_crs)
    shapes_with_height = [
        (geom, float(height))
        for geom, height in zip(buildings_proj.geometry, buildings_proj["height_m"])
        if geom is not None and not geom.is_empty
    ]
    if not shapes_with_height:
        raise RuntimeError("No valid building geometries available for rasterization.")

    building_raster = rasterize(
        shapes_with_height,
        out_shape=(profile["height"], profile["width"]),
        transform=profile["transform"],
        fill=0.0,
        dtype="float32",
    )

    dsm = dem_array.copy()
    nodata = profile["nodata"]
    valid_mask = dsm != nodata
    dsm[valid_mask] = dsm[valid_mask] + building_raster[valid_mask]
    LOGGER.info("DSM created successfully.")
    return dsm


def write_raster(array: np.ndarray, path: Path, profile: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = profile.copy()
    profile.update(dtype="float32", count=1)
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(array.astype("float32"), 1)
    LOGGER.info("Saved raster to %s", path)


def run_gdal_viewshed(
    dsm_path: Path,
    output_path: Path,
    observer_points_xy: Sequence[Tuple[float, float]],
    observer_height: float,
    target_height: float,
    gdal_bin: str,
    max_distance: float,
) -> None:
    LOGGER.info("Computing viewshed with %d observer point(s)…", len(observer_points_xy))
    output_path = output_path.resolve()
    if len(observer_points_xy) == 1:
        _call_gdal_viewshed(
            dsm_path,
            output_path,
            observer_points_xy[0],
            observer_height,
            target_height,
            gdal_bin,
            max_distance,
        )
        return

    with TemporaryDirectory() as tmpdir:
        tmp_paths = []
        for idx, point in enumerate(observer_points_xy):
            tmp_output = Path(tmpdir) / f"viewshed_{idx}.tif"
            _call_gdal_viewshed(
                dsm_path,
                tmp_output,
                point,
                observer_height,
                target_height,
                gdal_bin,
                max_distance,
            )
            tmp_paths.append(tmp_output)

        merge_viewsheds(tmp_paths, output_path)


def _call_gdal_viewshed(
    dsm_path: Path,
    output_path: Path,
    observer_xy: Tuple[float, float],
    observer_height: float,
    target_height: float,
    gdal_bin: str,
    max_distance: float,
) -> None:
    output_path = output_path.resolve()
    cmd = [
        gdal_bin,
        "-of",
        "GTiff",
        "-ox",
        str(observer_xy[0]),
        "-oy",
        str(observer_xy[1]),
        "-oz",
        str(observer_height),
        "-tz",
        str(target_height),
        "-vv",
        "1",
        "-iv",
        "0",
        "-ov",
        "0",
        "-a_nodata",
        "0",
    ]
    if max_distance and max_distance > 0:
        cmd.extend(["-md", str(max_distance)])
    cmd.extend([str(dsm_path), str(output_path)])
    LOGGER.debug("Running command: %s", " ".join(cmd))
    subprocess.run(cmd, check=True)
    LOGGER.info("Viewshed raster created at %s", output_path)


def merge_viewsheds(temp_paths: Iterable[Path], output_path: Path) -> None:
    temp_paths = list(temp_paths)
    LOGGER.info("Merging %d partial viewsheds…", len(temp_paths))
    data_arrays = []
    profile = None
    for path in temp_paths:
        with rasterio.open(path) as src:
            data_arrays.append(src.read(1))
            profile = src.profile if profile is None else profile
    merged = np.max(np.stack(data_arrays, axis=0), axis=0)
    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(merged.astype(profile["dtype"]), 1)
    LOGGER.info("Merged viewshed saved to %s", output_path)


def vectorize_visibility(raster_path: Path, output_path: Path) -> None:
    LOGGER.info("Vectorizing visible areas from %s…", raster_path)
    with rasterio.open(raster_path) as src:
        data = src.read(1)
        mask = data == 1
        geom_records = [
            shape(geom)
            for geom, value in shapes(data, mask=mask, transform=src.transform)
            if value == 1
        ]
        if not geom_records:
            LOGGER.warning("No visible pixels found to vectorize.")
            return
        polygons = gpd.GeoDataFrame(geometry=geom_records, crs=src.crs)
        dissolved = polygons.dissolve()
        flattened = dissolved.explode(index_parts=False)
        flattened = flattened.to_crs("EPSG:4326")
        driver = infer_vector_driver(output_path)
        flattened.to_file(output_path, driver=driver)
    LOGGER.info("Vector visibility polygons saved to %s", output_path)


def infer_vector_driver(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".geojson", ".json"}:
        return "GeoJSON"
    if suffix == ".gpkg":
        return "GPKG"
    if suffix == ".shp":
        return "ESRI Shapefile"
    raise ValueError(
        f"Unsupported vector extension '{path.suffix}'. Use .geojson, .gpkg, or .shp."
    )


def project_targets(
    points: Sequence[Tuple[float, float]], target_crs
) -> List[Tuple[float, float]]:
    transformer = Transformer.from_crs("EPSG:4326", target_crs, always_xy=True)
    projected = []
    for lat, lon in points:
        x, y = transformer.transform(lon, lat)
        projected.append((x, y))
    return projected


def main() -> None:
    args = parse_args()
    configure_logging(args.log_level)
    try:
        targets = parse_target_points(args)
        buffer_geom = create_buffer_polygon(targets, args.buffer_m)
        buildings = fetch_buildings(buffer_geom)
        dem_array, dem_profile = clip_dem_to_aoi(args.dem, buffer_geom)
        dsm_array = build_dsm(dem_array, dem_profile, buildings)

        observer_points_xy = project_targets(targets, dem_profile["crs"])
        max_distance = args.max_distance or args.buffer_m

        if args.dsm_output:
            dsm_path = args.dsm_output
            write_raster(dsm_array, dsm_path, dem_profile)
            run_gdal_viewshed(
                dsm_path,
                args.output,
                observer_points_xy,
                args.observer_height,
                args.target_height,
                args.gdal_bin,
                max_distance,
            )
        else:
            with TemporaryDirectory() as temp_dir:
                dsm_path = Path(temp_dir) / "dsm.tif"
                write_raster(dsm_array, dsm_path, dem_profile)
                run_gdal_viewshed(
                    dsm_path,
                    args.output,
                    observer_points_xy,
                    args.observer_height,
                    args.target_height,
                    args.gdal_bin,
                    max_distance,
                )

        if args.vector_output:
            vectorize_visibility(args.output, args.vector_output)

        LOGGER.info("Reverse viewshed finished successfully.")
    except Exception as exc:  # pylint: disable=broad-except
        LOGGER.error("Failed to generate reverse viewshed: %s", exc)
        raise


if __name__ == "__main__":
    main()

