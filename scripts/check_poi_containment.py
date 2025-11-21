#!/usr/bin/env python3
"""
Annotate the historical VK photo dataset with spatial flags showing whether
each point falls inside the expected POI area polygon and, more strictly,
inside the POI building footprint.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Dict, Optional

import pandas as pd
from shapely.geometry import Point, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"

POI_POLYGON_FILES: Dict[str, Dict[str, Path]] = {
    "or avner habad community center": {
        "area": DATA_DIR / "feor_view.geojson",
        "building": DATA_DIR / "feor_inside.geojson",
    },
    "synagogue": {
        "area": DATA_DIR / "synagogue_view.geojson",
        "building": DATA_DIR / "synagogue_inside.geojson",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Flag rows whose coordinates fall inside POI polygons."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DATA_DIR / "vk_photos_perm_historical.csv",
        help="Path to the historical dataset CSV.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DATA_DIR / "vk_photos_perm_historical_with_polygons.csv",
        help="Where to store the annotated CSV.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow overwriting the output file if it exists.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging for troubleshooting.",
    )
    return parser.parse_args()


def load_geojson_polygon(path: Path) -> BaseGeometry:
    with path.open("r", encoding="utf-8") as fp:
        data = json.load(fp)

    features = data.get("features", [])
    if not features:
        raise ValueError(f"No features found in {path}")

    geometries = [shape(feature["geometry"]) for feature in features]
    return unary_union(geometries) if len(geometries) > 1 else geometries[0]


def load_poi_polygons() -> Dict[str, Dict[str, Optional[BaseGeometry]]]:
    polygons: Dict[str, Dict[str, Optional[BaseGeometry]]] = {}

    for poi_name, layer_paths in POI_POLYGON_FILES.items():
        polygons[poi_name] = {}
        for layer_name, layer_path in layer_paths.items():
            if not layer_path.exists():
                logging.warning(
                    "GeoJSON file missing for %s (%s): %s",
                    poi_name,
                    layer_name,
                    layer_path,
                )
                polygons[poi_name][layer_name] = None
                continue

            polygons[poi_name][layer_name] = load_geojson_polygon(layer_path)

    return polygons


def normalize_poi_name(name: Optional[str]) -> Optional[str]:
    if name is None:
        return None
    normalized = name.strip().lower()
    return normalized or None


def annotate_dataset(
    df: pd.DataFrame,
    polygons: Dict[str, Dict[str, Optional[BaseGeometry]]],
) -> pd.DataFrame:
    df = df.copy()
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["long"] = pd.to_numeric(df["long"], errors="coerce")

    inside_area = []
    inside_building = []
    missing_pois = set()

    for row in df.itertuples(index=False):
        lat = getattr(row, "lat")
        lon = getattr(row, "long")
        poi_name = normalize_poi_name(getattr(row, "poi_name"))

        if pd.isna(lat) or pd.isna(lon) or poi_name is None:
            inside_area.append(False)
            inside_building.append(False)
            continue

        poi_polygons = polygons.get(poi_name)
        if not poi_polygons:
            inside_area.append(False)
            inside_building.append(False)
            missing_pois.add(poi_name)
            continue

        point = Point(float(lon), float(lat))
        area_polygon = poi_polygons.get("area")
        building_polygon = poi_polygons.get("building")

        inside_area.append(bool(area_polygon.covers(point)) if area_polygon else False)
        inside_building.append(
            bool(building_polygon.covers(point)) if building_polygon else False
        )

    if missing_pois:
        logging.warning(
            "Encountered %d POI names without configured polygons: %s",
            len(missing_pois),
            ", ".join(sorted(missing_pois)),
        )

    df["inside_poi_area"] = inside_area
    df["inside_poi_building"] = inside_building
    return df


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    if not args.input.exists():
        raise FileNotFoundError(f"Input dataset not found: {args.input}")

    if args.output.exists() and not args.overwrite:
        raise FileExistsError(
            f"Output file already exists: {args.output} (pass --overwrite to replace it)"
        )

    logging.info("Loading dataset from %s", args.input)
    df = pd.read_csv(args.input)

    logging.info("Loading POI polygons")
    polygons = load_poi_polygons()

    logging.info("Annotating %d rows", len(df))
    annotated_df = annotate_dataset(df, polygons)

    inside_area_count = int(annotated_df["inside_poi_area"].sum())
    inside_building_count = int(annotated_df["inside_poi_building"].sum())

    annotated_df.to_csv(args.output, index=False)
    logging.info("Saved annotated dataset to %s", args.output)
    logging.info(
        "Rows inside POI area: %d (%.2f%%)",
        inside_area_count,
        inside_area_count / max(len(annotated_df), 1) * 100,
    )
    logging.info(
        "Rows inside POI building: %d (%.2f%%)",
        inside_building_count,
        inside_building_count / max(len(annotated_df), 1) * 100,
    )


if __name__ == "__main__":
    main()


