#!/usr/bin/env python3
"""
VK photo enrichment and evaluation tool.

This script restructures the collected VK photo dataset, augments it with
additional metadata (user profile info, hashtags, sibling-photo links), runs a
multimodal model to produce annotations, and provides helpers to bootstrap and
evaluate a golden set.
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import re
import sys
import textwrap
import time
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Literal, Optional, Sequence, Set, Tuple, Type
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import pandas as pd
from pandas.api.types import is_bool_dtype
import requests
from pydantic import BaseModel, Field  # type: ignore

try:
    from openai import OpenAI  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    OpenAI = None

VK_API_VERSION = "5.131"
DEFAULT_CACHE_DIR = Path("cache/enrichment")
DEFAULT_MODEL_CACHE = DEFAULT_CACHE_DIR / "model_responses"
DEFAULT_USER_CACHE = DEFAULT_CACHE_DIR / "users.json"
DEFAULT_BATCH_INPUT = DEFAULT_CACHE_DIR / "openai_batch_input.jsonl"
DEFAULT_BATCH_MANIFEST = DEFAULT_CACHE_DIR / "openai_batch_manifest.json"

MODEL_PRICING_USD_PER_1K = {
    "gpt-5.1": {"input": 0.00125, "output": 0.01},
    "gpt-5": {"input": 0.00125, "output": 0.01},
    "gpt-5-mini": {"input": 0.00025, "output": 0.002},
    "gpt-5-nano": {"input": 0.00005, "output": 0.0004},
    "gpt-5.1-chat-latest": {"input": 0.00125, "output": 0.01},
    "gpt-5-chat-latest": {"input": 0.00125, "output": 0.01},
    "gpt-5.1-codex": {"input": 0.00125, "output": 0.01},
    "gpt-5-codex": {"input": 0.00125, "output": 0.01},
    "gpt-5-pro": {"input": 0.015, "output": 0.12},
    "gpt-4.1": {"input": 0.002, "output": 0.008},
    "gpt-4.1-mini": {"input": 0.0004, "output": 0.0016},
    "gpt-4.1-nano": {"input": 0.0001, "output": 0.0004},
    "gpt-4o": {"input": 0.0025, "output": 0.01},
    "gpt-4o-2024-05-13": {"input": 0.005, "output": 0.015},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4o-mini-2024-07-18": {"input": 0.0003, "output": 0.0012},
    "gpt-4o-mini-search-preview": {"input": 0.00015, "output": 0.0006},
    "gpt-4o-search-preview": {"input": 0.0025, "output": 0.01},
    "gpt-4o-mini-realtime-preview": {"input": 0.0006, "output": 0.0024},
    "gpt-4o-realtime-preview": {"input": 0.005, "output": 0.02},
    "gpt-4o-mini-audio-preview": {"input": 0.00015, "output": 0.0006},
    "gpt-4o-audio-preview": {"input": 0.0025, "output": 0.01},
    "gpt-4o-mini-tts": {"input": 0.0006, "output": 0.012},
    "gpt-4o-transcribe": {"input": 0.0025, "output": 0.01},
    "gpt-4o-mini-transcribe": {"input": 0.00125, "output": 0.005},
    "gpt-4o-mini-tts": {"input": 0.0006, "output": 0.012},
    "gpt-4o-mini-transcribe": {"input": 0.003, "output": 0.012},
    "gpt-4o-mini-tts": {"input": 0.0006, "output": 0.012},
    "gpt-4o-mini-transcribe-diarize": {"input": 0.003, "output": 0.012},
    "o1": {"input": 0.015, "output": 0.06},
    "o1-mini": {"input": 0.0011, "output": 0.0044},
    "o1-pro": {"input": 0.15, "output": 0.6},
    "o3": {"input": 0.002, "output": 0.008},
    "o3-pro": {"input": 0.02, "output": 0.08},
    "o3-deep-research": {"input": 0.01, "output": 0.04},
    "o3-mini": {"input": 0.0011, "output": 0.0044},
    "o4-mini": {"input": 0.0011, "output": 0.0044},
    "o4-mini-deep-research": {"input": 0.002, "output": 0.008},
    "gpt-4.1-2025-04-14": {"input": 0.003, "output": 0.012},
    "gpt-4.1-mini-2025-04-14": {"input": 0.0008, "output": 0.0032},
    "gpt-4.1-nano-2025-04-14": {"input": 0.0002, "output": 0.0008},
    "gpt-4o-2024-08-06": {"input": 0.00375, "output": 0.015},
    "gpt-4o-mini-2024-08-06": {"input": 0.0003, "output": 0.0012},
    "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
    "gpt-3.5-turbo-0125": {"input": 0.0005, "output": 0.0015},
    "gpt-3.5-turbo-1106": {"input": 0.001, "output": 0.002},
    "gpt-3.5-turbo-0613": {"input": 0.0015, "output": 0.002},
    "gpt-3.5-0301": {"input": 0.0015, "output": 0.002},
}


ANNOTATION_FIELDS = [
    "annotation_text_description",
    "annotation_location_type",
    "annotation_photo_type",
    "annotation_is_advertisement",
    "annotation_city_objects",
    "annotation_city_activities",
    "annotation_user_intent",
    "annotation_has_building",
    "annotation_has_synagogue",
    "annotation_has_feor",
    "annotation_has_other_building",
    "annotation_confidence",
    "model_version",
    "model_timestamp",
]

CSV_COLUMNS = [
    "photo_id",
    "owner_id",
    "album_id",
    "post_id",
    "post_url",
    "image_url",
    "related_photo_urls",
    "hashtags",
    "date_human",
    "lat",
    "long",
    "poi_lat",
    "poi_lon",
    "distance_meters",
    "poi_name",
    "user_id",
    "user_gender",
    "user_age",
    "user_city",
    "user_city_id",
    "user_kind",
    "post_text",
    "inside_poi_area",
    "inside_poi_building",
] + ANNOTATION_FIELDS


class PhotoAnnotationModel(BaseModel):
    annotation_text_description: str
    annotation_location_type: Literal["indoor", "outdoor", "unknown", "mixed"]
    annotation_photo_type: Literal[
        "portrait",
        "selfie",
        "group_portrait",
        "interior",
        "cityscape",
        "product",
        "urban_detail",
        "food",
        "animal",
        "building",
        "other",
    ]
    annotation_is_advertisement: bool
    annotation_city_objects: str
    annotation_city_activities: str
    annotation_user_intent: str
    annotation_has_building: bool
    annotation_has_synagogue: bool
    annotation_has_feor: bool
    annotation_has_other_building: bool
    annotation_confidence: float = Field(ge=0.0, le=1.0)
    model_config = {"extra": "forbid"}


class BuildingVerificationModel(BaseModel):
    matches_reference: bool
    verification_confidence: float = Field(ge=0.0, le=1.0)
    model_config = {"extra": "forbid"}


def add_dataset_common_args(
    parser: argparse.ArgumentParser, include_subset_controls: bool = True
) -> None:
    parser.add_argument(
        "--input-csv",
        type=Path,
        default=Path("vk_photos_perm_historical_with_polygons.csv"),
        help="Dataset with spatial flags produced by check_poi_containment.py",
    )
    parser.add_argument(
        "--vk-token",
        type=str,
        default=os.environ.get("VK_TOKEN"),
        help="VK API token; falls back to VK_TOKEN env variable.",
    )
    parser.add_argument(
        "--skip-user-fetch",
        action="store_true",
        help="Skip VK user metadata fetch (keeps user columns empty).",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=DEFAULT_CACHE_DIR,
        help="Base directory for cached model responses and user data.",
    )
    if include_subset_controls:
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Process only the first N photos (useful for dry runs).",
        )
        parser.add_argument(
            "--shuffle",
            action="store_true",
            help="Randomize processing order to balance model load.",
        )


def add_reference_image_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--reference-synagogue",
        action="append",
        default=None,
        metavar="PATH_OR_URL",
        help="Optional URL or local path with canonical synagogue photo (repeatable).",
    )
    parser.add_argument(
        "--reference-feor",
        action="append",
        default=None,
        metavar="PATH_OR_URL",
        help="Optional URL or local path with canonical FEOR building photo (repeatable).",
    )


def add_openai_client_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--openai-base-url",
        type=str,
        default=None,
        help="Custom OpenAI-compatible base URL (for local gateways).",
    )
    parser.add_argument(
        "--openai-api-key",
        type=str,
        default=os.environ.get("OPENAI_API_KEY"),
        help="API key for OpenAI or compatible provider.",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enrich VK photo dataset with multimodal annotations."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # annotate command
    annotate = subparsers.add_parser(
        "annotate",
        help="Run the enrichment pipeline and write an augmented CSV.",
    )
    add_dataset_common_args(annotate)
    annotate.add_argument(
        "--output-csv",
        type=Path,
        default=Path("vk_photos_perm_enriched.csv"),
        help="Destination CSV with enriched annotations.",
    )
    annotate.add_argument(
        "--model-responses",
        type=Path,
        default=Path("vk_photos_perm_enriched.model_responses.jsonl"),
        help="Path to write raw model responses for auditing.",
    )
    annotate.add_argument(
        "--model-provider",
        choices=["none", "openai"],
        default="none",
        help="Multimodal provider to use for annotations.",
    )
    annotate.add_argument(
        "--model-name",
        type=str,
        default="gpt-4o-mini",
        help="Model identifier for the multimodal provider.",
    )
    add_openai_client_args(annotate)
    add_reference_image_args(annotate)
    annotate.add_argument(
        "--checkpoint-file",
        type=Path,
        default=DEFAULT_CACHE_DIR / "annotate_checkpoint.json",
        help="JSON checkpoint to resume annotation progress.",
    )
    annotate.add_argument(
        "--checkpoint-interval",
        type=int,
        default=25,
        help="How many photos to process before writing checkpoint data.",
    )
    annotate.add_argument(
        "--resume",
        action="store_true",
        help="Respect cached model responses and skip already annotated photos.",
    )
    annotate.add_argument(
        "--only-photo-id",
        action="append",
        dest="only_photo_ids",
        default=None,
        metavar="PHOTO_ID",
        help="Annotate only the specified photo_id (repeatable).",
    )

    batch = subparsers.add_parser(
        "openai-batch",
        help="Prepare, submit, and consume OpenAI Batch API jobs.",
    )
    batch_sub = batch.add_subparsers(dest="batch_command", required=True)

    batch_prepare = batch_sub.add_parser(
        "prepare",
        help="Convert the dataset into an OpenAI Batch input file.",
    )
    add_dataset_common_args(batch_prepare)
    add_reference_image_args(batch_prepare)
    batch_prepare.add_argument(
        "--model-name",
        type=str,
        default="gpt-4o-mini",
        help="Model identifier to use inside the batch job.",
    )
    batch_prepare.add_argument(
        "--batch-input",
        type=Path,
        default=DEFAULT_BATCH_INPUT,
        help="Destination .jsonl file with batch requests.",
    )
    batch_prepare.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_BATCH_MANIFEST,
        help="Path to write the manifest that maps custom_ids to photo_ids.",
    )
    batch_prepare.add_argument(
        "--only-missing-annotations",
        action="store_true",
        help="Restrict the batch to rows where the target annotation column is empty.",
    )
    batch_prepare.add_argument(
        "--missing-annotation-column",
        type=str,
        default="annotation_text_description",
        help="Column used to determine whether a row already has annotations.",
    )
    batch_prepare.add_argument(
        "--enable-building-verification",
        action="store_true",
        help="Also enqueue building-verification prompts for flagged rows.",
    )
    batch_prepare.add_argument(
        "--only-building-verification",
        action="store_true",
        help="Submit only building-verification requests (no fresh annotations).",
    )
    batch_prepare.add_argument(
        "--only-building-flagged",
        action="store_true",
        help="Process only rows where the building flag column is truthy.",
    )
    batch_prepare.add_argument(
        "--building-flag-column",
        type=str,
        default="annotation_has_building",
        help="Column whose truthy rows should receive building verification.",
    )

    batch_apply = batch_sub.add_parser(
        "apply",
        help="Merge a completed Batch output file back into the dataset.",
    )
    add_dataset_common_args(batch_apply, include_subset_controls=False)
    batch_apply.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_BATCH_MANIFEST,
        help="Manifest produced by the prepare command.",
    )
    batch_apply.add_argument(
        "--batch-output",
        type=Path,
        required=True,
        help="Output JSONL downloaded from OpenAI (contains successful responses).",
    )
    batch_apply.add_argument(
        "--batch-errors",
        type=Path,
        default=None,
        help="Optional JSONL file with failed/expired requests.",
    )
    batch_apply.add_argument(
        "--output-csv",
        type=Path,
        default=Path("vk_photos_perm_enriched.csv"),
        help="Destination CSV with merged annotations.",
    )
    batch_apply.add_argument(
        "--model-responses",
        type=Path,
        default=Path("vk_photos_perm_enriched.model_responses.jsonl"),
        help="Where to store flattened model responses for auditing.",
    )

    batch_upload = batch_sub.add_parser(
        "upload",
        help="Upload a prepared batch JSONL via the Files API.",
    )
    add_openai_client_args(batch_upload)
    batch_upload.add_argument(
        "--file-path",
        type=Path,
        default=DEFAULT_BATCH_INPUT,
        help="Local batch input JSONL to upload.",
    )

    batch_create = batch_sub.add_parser(
        "create",
        help="Create a Batch job using a previously uploaded file.",
    )
    add_openai_client_args(batch_create)
    batch_create.add_argument(
        "--input-file-id",
        type=str,
        required=True,
        help="File ID returned by the upload step.",
    )
    batch_create.add_argument(
        "--endpoint",
        type=str,
        default="/v1/responses",
        help="Target endpoint for the batch job.",
    )
    batch_create.add_argument(
        "--completion-window",
        type=str,
        default="24h",
        help="Completion window requested from the API (currently only 24h).",
    )
    batch_create.add_argument(
        "--metadata",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Optional metadata entries to attach to the batch (repeatable).",
    )

    batch_status = batch_sub.add_parser(
        "status",
        help="Retrieve the latest status for a batch ID.",
    )
    add_openai_client_args(batch_status)
    batch_status.add_argument(
        "--batch-id",
        type=str,
        required=True,
        help="Batch identifier returned by the create step.",
    )

    batch_results = batch_sub.add_parser(
        "results",
        help="Download a file (output or error) produced by a Batch job.",
    )
    add_openai_client_args(batch_results)
    batch_results.add_argument(
        "--file-id",
        type=str,
        required=True,
        help="ID of the file to download (output_file_id or error_file_id).",
    )
    batch_results.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Where to store the downloaded file.",
    )

    batch_cancel = batch_sub.add_parser(
        "cancel",
        help="Cancel an in-flight batch job.",
    )
    add_openai_client_args(batch_cancel)
    batch_cancel.add_argument(
        "--batch-id",
        type=str,
        required=True,
        help="Identifier of the batch to cancel.",
    )

    batch_list = batch_sub.add_parser(
        "list",
        help="List recent batch jobs.",
    )
    add_openai_client_args(batch_list)
    batch_list.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of batches to display.",
    )
    batch_list.add_argument(
        "--after",
        type=str,
        default=None,
        help="Pagination cursor to continue listing.",
    )

    batch_sequential = batch_sub.add_parser(
        "sequential",
        help="Split the dataset into fixed-size chunks and submit batches sequentially.",
    )
    add_dataset_common_args(batch_sequential)
    add_reference_image_args(batch_sequential)
    add_openai_client_args(batch_sequential)
    batch_sequential.add_argument(
        "--model-name",
        type=str,
        default="gpt-4o-mini",
        help="Model identifier to use inside the batch job.",
    )
    batch_sequential.add_argument(
        "--chunk-size",
        type=int,
        default=500,
        help="Number of rows per batch chunk.",
    )
    batch_sequential.add_argument(
        "--max-chunks",
        type=int,
        default=None,
        help="Optional limit on how many chunks to submit (useful for dry runs).",
    )
    batch_sequential.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_CACHE_DIR / "batch_chunks",
        help="Directory to store chunk inputs, manifests, and outputs.",
    )
    batch_sequential.add_argument(
        "--endpoint",
        type=str,
        default="/v1/responses",
        help="Target endpoint for the batch job.",
    )
    batch_sequential.add_argument(
        "--completion-window",
        type=str,
        default="24h",
        help="Completion window requested from the API (currently only 24h).",
    )
    batch_sequential.add_argument(
        "--poll-interval",
        type=int,
        default=60,
        help="Seconds to wait between status polls.",
    )
    batch_sequential.add_argument(
        "--metadata",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Optional metadata entries to attach to each batch (repeatable).",
    )
    batch_sequential.add_argument(
        "--only-missing-annotations",
        action="store_true",
        help="Restrict chunk submission to rows lacking annotations.",
    )
    batch_sequential.add_argument(
        "--missing-annotation-column",
        type=str,
        default="annotation_text_description",
        help="Column used to detect missing annotations.",
    )
    batch_sequential.add_argument(
        "--enable-building-verification",
        action="store_true",
        help="Include building-verification prompts for flagged rows.",
    )
    batch_sequential.add_argument(
        "--only-building-verification",
        action="store_true",
        help="Submit only building-verification requests (skip annotation prompts).",
    )
    batch_sequential.add_argument(
        "--only-building-flagged",
        action="store_true",
        help="Submit chunks only for rows where the building flag column is truthy.",
    )
    batch_sequential.add_argument(
        "--building-flag-column",
        type=str,
        default="annotation_has_building",
        help="Column whose truthy rows should receive building verification.",
    )

    # golden draft command
    draft = subparsers.add_parser(
        "golden-draft", help="Create a semi-automatic golden set draft."
    )
    draft.add_argument(
        "--enriched-csv",
        type=Path,
        required=True,
        help="Enriched CSV produced by the annotate command.",
    )
    draft.add_argument(
        "--output-dir",
        type=Path,
        default=Path("golden_set"),
        help="Directory to store the draft CSV.",
    )
    draft.add_argument(
        "--sample-size",
        type=int,
        default=75,
        help="Number of photos to include in the draft.",
    )
    draft.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for sampling.",
    )
    draft.add_argument(
        "--strategy",
        choices=["random", "recent", "inside_poi_area", "unique_by_user"],
        default="random",
        help="Sampling strategy for draft selection.",
    )

    # golden apply command
    apply_cmd = subparsers.add_parser(
        "golden-apply",
        help="Convert a reviewed draft into the canonical golden set file.",
    )
    apply_cmd.add_argument(
        "--reviewed-csv",
        type=Path,
        required=True,
        help="Draft CSV with reviewer-edited columns (human_*).",
    )
    apply_cmd.add_argument(
        "--golden-csv",
        type=Path,
        default=Path("golden_set/golden_labels.csv"),
        help="Canonical golden set output file.",
    )

    # evaluate command
    evaluate = subparsers.add_parser(
        "evaluate",
        help="Compare an enriched CSV against the approved golden set.",
    )
    evaluate.add_argument(
        "--predictions",
        type=Path,
        required=True,
        help="Enriched CSV to evaluate.",
    )
    evaluate.add_argument(
        "--golden-csv",
        type=Path,
        default=Path("golden_set/golden_labels.csv"),
        help="Approved golden set with human labels.",
    )
    evaluate.add_argument(
        "--report-json",
        type=Path,
        default=Path("golden_set/eval_report.json"),
        help="Where to save evaluation summary.",
    )

    return parser.parse_args()


# ---------------------------------------------------------------------------
# Helpers


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def extract_hashtags(text: str) -> List[str]:
    if not isinstance(text, str) or not text:
        return []
    hashtag_pattern = re.compile(r"#([\w\d_]+)", re.UNICODE)
    return sorted({match.group(1) for match in hashtag_pattern.finditer(text)})


def ensure_text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def select_preferred_size(size_values: List[str], target_width: int = 480) -> Optional[str]:
    best_value = None
    best_diff = None
    for size in size_values:
        size_clean = size.strip()
        if "x" not in size_clean:
            continue
        try:
            width = int(size_clean.lower().split("x", 1)[0])
        except ValueError:
            continue
        diff = abs(width - target_width)
        if best_diff is None or diff < best_diff:
            best_diff = diff
            best_value = size_clean
        elif diff == best_diff and best_value:
            try:
                best_width = int(best_value.lower().split("x", 1)[0])
            except ValueError:
                best_width = width
            if width < best_width:
                best_value = size_clean
    return best_value


def build_resized_image_url(image_url: str, target_width: int = 480) -> str:
    if not image_url or not isinstance(image_url, str):
        return image_url
    parsed = urlsplit(image_url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    as_values = query.get("as", [])
    candidate_sizes: List[str] = []
    if as_values:
        for raw in as_values:
            candidate_sizes.extend([entry for entry in raw.split(",") if entry])
    preferred = select_preferred_size(candidate_sizes, target_width=target_width)
    if not preferred:
        return image_url
    query["cs"] = [preferred]
    new_query = urlencode(query, doseq=True)
    return urlunsplit(parsed._replace(query=new_query))


def _normalize_id_component(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, float):
        if value.is_integer():
            value = int(value)
    return str(value)


def _sanitize_key_component(component: str) -> str:
    return re.sub(r"[^0-9A-Za-z_.:-]", "_", component)


def build_photo_key(owner_id: Any, photo_id: Any) -> str:
    owner_component = _sanitize_key_component(
        _normalize_id_component(owner_id) or "owner-unknown"
    )
    photo_component = _sanitize_key_component(
        _normalize_id_component(photo_id) or "photo-unknown"
    )
    return f"{owner_component}__{photo_component}"


def resolve_building_focus(poi_name: Optional[str]) -> Optional[str]:
    if not poi_name or not isinstance(poi_name, str):
        return None
    name = poi_name.lower()
    if any(token in name for token in ["feor", "феор", "f.e.o.r", "f e o r"]):
        return "feor"
    if "synagogue" in name or "синагог" in name:
        return "synagogue"
    return None


def build_post_url(owner_id: Any, post_id: Any) -> Optional[str]:
    if pd.isna(post_id):
        return None
    try:
        owner_id_int = int(owner_id)
        post_id_int = int(float(post_id))
    except (TypeError, ValueError):
        return None
    return f"https://vk.com/wall{owner_id_int}_{post_id_int}"


def coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        if pd.isna(value):
            return False
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"", "0", "false", "no", "none", "null"}:
            return False
        return normalized in {"true", "1", "yes", "y", "t"}
    if pd.isna(value):
        return False
    return False


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Input CSV not found: {path}")
    df = pd.read_csv(path)
    logging.info("Loaded %d rows from %s", len(df), path)
    return df


def normalize_related_links(df: pd.DataFrame) -> Dict[str, List[str]]:
    related: Dict[str, List[str]] = {}
    if "post_id" not in df.columns:
        return related
    grouped = df.groupby("post_id")
    for pid, group in grouped:
        if pd.isna(pid):
            continue
        urls = group["image_url"].dropna().tolist()
        related[str(pid)] = urls
    return related


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_annotation() -> Dict[str, Any]:
    now = utc_now_iso()
    return {
        "annotation_text_description": "",
        "annotation_location_type": "unknown",
        "annotation_photo_type": "",
        "annotation_is_advertisement": False,
        "annotation_city_objects": "",
        "annotation_city_activities": "",
        "annotation_user_intent": "",
        "annotation_has_building": False,
        "annotation_has_synagogue": False,
        "annotation_has_feor": False,
        "annotation_has_other_building": False,
        "annotation_confidence": 0.0,
        "model_version": "",
        "model_timestamp": now,
    }


def estimate_usage_cost(model: str, input_tokens: Optional[int], output_tokens: Optional[int]) -> Optional[float]:
    pricing = MODEL_PRICING_USD_PER_1K.get(model)
    if not pricing:
        return None
    input_rate = pricing.get("input", 0.0)
    output_rate = pricing.get("output", 0.0)
    cost = 0.0
    if input_tokens:
        cost += (input_tokens / 1000.0) * input_rate
    if output_tokens:
        cost += (output_tokens / 1000.0) * output_rate
    return round(cost, 6)


# ---------------------------------------------------------------------------
# Annotation checkpoint helpers


class AnnotationCheckpoint:
    def __init__(self, path: Path):
        self.path = path
        self.completed: Set[str] = set()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            ids = data.get("completed_photo_ids", [])
            self.completed = set(str(pid) for pid in ids)
        except json.JSONDecodeError:
            logging.warning("Checkpoint file %s is corrupted. Ignoring.", self.path)
            self.completed = set()

    def mark_complete(self, photo_id: str) -> None:
        self.completed.add(str(photo_id))

    def should_skip(self, photo_id: str) -> bool:
        return str(photo_id) in self.completed

    def save(self) -> None:
        ensure_directory(self.path.parent)
        payload = {
            "completed_photo_ids": sorted(self.completed),
            "updated_at": utc_now_iso(),
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def reset_file(self) -> None:
        self.completed.clear()
        if self.path.exists():
            try:
                self.path.unlink()
            except OSError as exc:
                logging.warning("Failed to remove checkpoint %s: %s", self.path, exc)


# ---------------------------------------------------------------------------
# VK user metadata


class VKUserMetadataFetcher:
    def __init__(self, token: Optional[str], cache_file: Path):
        self.token = token
        self.cache_file = cache_file
        self.cache: Dict[str, Dict[str, Any]] = {}
        if cache_file.exists():
            try:
                self.cache = json.loads(cache_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                logging.warning("User cache %s is corrupted. Rebuilding.", cache_file)
                self.cache = {}

    def save(self) -> None:
        if not self.cache_file.parent.exists():
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self.cache_file.write_text(json.dumps(self.cache, ensure_ascii=False, indent=2), encoding="utf-8")

    def enrich(self, user_ids: Iterable[Any]) -> Dict[str, Dict[str, Any]]:
        if not self.token:
            logging.warning("VK token missing; user metadata will remain empty.")
            return {}

        normalized_ids = [
            str(int(uid))
            for uid in user_ids
            if not pd.isna(uid)
         ]
        results: Dict[str, Dict[str, Any]] = {}
        missing: List[str] = []
        for uid in normalized_ids:
            if uid in self.cache:
                results[uid] = self.cache[uid]
            else:
                missing.append(uid)

        if not missing:
            return results

        # Only fetch real user IDs (positive). Negative IDs are communities.
        user_ids_real = [uid for uid in missing if not uid.startswith("-")]
        if user_ids_real:
            results.update(
                self._fetch_users(user_ids_real)
            )

        # Mark groups
        for uid in missing:
            if uid.startswith("-"):
                results[uid] = {
                    "user_kind": "group",
                    "user_gender": "unknown",
                    "user_age": None,
                    "user_city": None,
                    "user_city_id": None,
                }

        self.cache.update(results)
        self.save()
        return results

    def _fetch_users(self, user_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        batch_size = 500
        output: Dict[str, Dict[str, Any]] = {}
        session = requests.Session()

        for i in range(0, len(user_ids), batch_size):
            batch = user_ids[i : i + batch_size]
            params = {
                "access_token": self.token,
                "v": VK_API_VERSION,
                "user_ids": ",".join(batch),
                "fields": "sex,bdate,city",
            }
            response = session.get(
                "https://api.vk.com/method/users.get", params=params, timeout=15
            )
            data = response.json()
            if "error" in data:
                logging.error("VK users.get error: %s", data["error"])
                continue
            for user in data.get("response", []):
                uid = str(user.get("id"))
                output[uid] = self._normalize_user(user)

            time.sleep(0.34)  # stay gentle with API

        return output

    @staticmethod
    def _normalize_user(user: Dict[str, Any]) -> Dict[str, Any]:
        sex_map = {1: "female", 2: "male"}
        gender = sex_map.get(user.get("sex"), "unknown")
        age = None
        bdate = user.get("bdate")
        if bdate and bdate.count(".") == 2:  # includes year
            try:
                dob = datetime.strptime(bdate, "%d.%m.%Y")
                today = datetime.now(timezone.utc)
                age = today.year - dob.year - (
                    (today.month, today.day) < (dob.month, dob.day)
                )
            except ValueError:
                pass

        city_obj = user.get("city") or {}
        return {
            "user_kind": "person",
            "user_gender": gender,
            "user_age": age,
            "user_city": city_obj.get("title"),
            "user_city_id": city_obj.get("id"),
        }


# ---------------------------------------------------------------------------
# Multimodal model integration


class MultimodalModelClient:
    def annotate(self, photo_row: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError


@dataclass
class AnnotationPromptBundle:
    content: List[Dict[str, Any]]
    image_for_model: Optional[str]
    building_focus: Optional[str]
    poi_label: str


def build_annotation_prompt_bundle(photo_row: Dict[str, Any]) -> AnnotationPromptBundle:
    poi_name = ensure_text(photo_row.get("poi_name"))
    building_focus = resolve_building_focus(poi_name)
    poi_label = poi_name or "неизвестный POI"

    prompt = textwrap.dedent(
        """
                Ты — специалист по описанию и классификации городских фотографий из социальных сетей.

        Проанализируй изображение (и текстовый контекст, если он есть) и верни строго ОДИН JSON-объект указанной структуры.
        Не добавляй ничего, что не видно на изображении или не подтверждается текстовым контекстом.
        Если данных недостаточно — используй "unknown", пустую строку или false.

        photo_type — одно значение:
        "portrait", "selfie", "group_portrait", "interior", "cityscape",
        "product", "urban_detail", "food", "animal", "building", "other".

        Уточнения:
        - "building" — здание является главным объектом и видно целиком/почти целиком.
        - "cityscape" — широкий городской план; здания — часть окружения.
        - "urban_detail" — крупный план городской среды, но не товар.
        - "product" — объект выглядит как товар/услуга, подготовленный или продемонстрированный.

        location_type: "indoor", "outdoor", "mixed", "unknown".

        is_advertising:
        true — реклама товара/услуги; false — бытовое/репортажное фото.

        Поле "user_intent": сжато опиши визуально считываемую цель снимка (главный объект, ракурс, композиция). Не выдумывай мотивацию. Примеры: "показать одежду", "задокументировать городскую сцену", "показать товар", "показать еду", "сделать селфи", "поделиться впечатлением от поездки".

        Поле "urban_elements": перечисли объекты городской среды короткими, однотипными сущностями.
        Поле "urban_practices": перечисли различимые городские активности.
        Если объектов/активностей нет — пустая строка.

        has_buildings: true/false на основе визуального наличия здания или его части.

        annotation_confidence — число от 0 до 1, отражающее твою уверенность в аннотации в целом.

        Пример формата:
        {
            "annotation_text_description": "Фасад кирпичного здания на улице, люди идут по тротуару",
            "annotation_location_type": "outdoor",
            "annotation_photo_type": "cityscape",
            "annotation_is_advertisement": false,
            "annotation_city_objects": "тротуар, дорога, фасад здания, вывеска",
            "annotation_city_activities": "прогулка",
            "annotation_user_intent": "задокументировать городскую сцену",
            "annotation_has_building": true,
            "annotation_confidence": 0.83
        }
        """
    ).strip()

    content = [
        {"type": "input_text", "text": prompt},
        {
            "type": "input_text",
            "text": (
                "Дополнительный контекст: "
                f"описание поста: {photo_row.get('post_text', '') or 'нет описания'}. "
            ),
        },
    ]

    resized_image_url = build_resized_image_url(
        photo_row.get("image_url"), target_width=360
    )
    image_for_model = resized_image_url or photo_row.get("image_url")
    content.append(
        {
            "type": "input_image",
            "image_url": image_for_model,
        }
    )
    return AnnotationPromptBundle(
        content=content,
        image_for_model=image_for_model,
        building_focus=building_focus,
        poi_label=poi_label,
    )


def build_building_verification_content(
    image_url: Optional[str],
    building_focus: str,
    poi_label: str,
    references: Sequence[Tuple[str, Dict[str, str]]],
) -> Optional[List[Dict[str, Any]]]:
    if not image_url or not references:
        return None
    prompt = textwrap.dedent(
        f"""
        Ты сравниваешь здание на фото с несколькими эталонными изображениями объекта "{building_focus}".
        Все эталонные фото показывают один и тот же объект, но с разных ракурсов, в разные годы, времена суток или состояния (исторический и современный вид).
        Ответь только JSON-объектом:
        {{
          "matches_reference": boolean,
          "verification_confidence": number (0-1)
        }}
        Установи matches_reference=true, если целевой объект совпадает хотя бы с одним эталонным изображением, даже если:
        - объект виден частично или не является главным фокусом,
        - ракурс, масштаб или освещение отличаются,
        - на фото показан исторический вариант объекта, отличающийся от современного вида
        Используй характерные архитектурные элементы, пропорции, детали фасада, окружение.
        """
    ).strip()

    content: List[Dict[str, Any]] = [
        {"type": "input_text", "text": prompt},
        {"type": "input_text", "text": f"POI: {poi_label}"},
        {"type": "input_image", "image_url": image_url},
    ]
    for idx, (label, payload) in enumerate(references, start=1):
        content.append(
            {
                "type": "input_text",
                "text": f"Справочное изображение #{idx} ({building_focus}): {label}",
            }
        )
        content.append(dict(payload))
    return content


def json_schema_response_format(model_cls: Type[BaseModel]) -> Dict[str, Any]:
    schema = model_cls.model_json_schema()
    return {
        "type": "json_schema",
        "strict": True,
        "name": model_cls.__name__,
        "schema": schema,
    }


class OpenAIMultimodalClient(MultimodalModelClient):
    def __init__(
        self,
        model_name: str,
        api_key: Optional[str],
        base_url: Optional[str],
        reference_images: Sequence[Tuple[str, str, Dict[str, str]]] = (),
    ):
        if OpenAI is None:
            raise RuntimeError("openai package is required but not installed.")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for model inference.")
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model_name = model_name
        self.reference_images = list(reference_images)
        self.reference_map: Dict[str, List[Tuple[str, Dict[str, str]]]] = {}
        for kind, label, payload in self.reference_images:
            self.reference_map.setdefault(kind, []).append((label, payload))

    def annotate(self, photo_row: Dict[str, Any]) -> Dict[str, Any]:
        bundle = build_annotation_prompt_bundle(photo_row)

        start_time = time.perf_counter()
        try:
            response = self.client.responses.parse(
                model=self.model_name,
                input=[
                    {
                        "role": "user",
                        "content": bundle.content,
                    }
                ],
                text_format=PhotoAnnotationModel,
            )
            parsed = response.output_parsed.model_dump()
            elapsed = time.perf_counter() - start_time
        except Exception as exc:  # pragma: no cover - network errors
            logging.error(
                "Failed to parse multimodal response for photo %s: %s",
                photo_row.get("photo_id"),
                exc,
            )
            return default_annotation()

        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "input_tokens", None) if usage else None
        if input_tokens is None and usage:
            input_tokens = getattr(usage, "prompt_tokens", None)
        output_tokens = getattr(usage, "output_tokens", None) if usage else None
        if output_tokens is None and usage:
            output_tokens = getattr(usage, "completion_tokens", None)
        est_cost = estimate_usage_cost(self.model_name, input_tokens, output_tokens)
        photo_id = photo_row.get("photo_id")
        log_message = f"OpenAI {self.model_name} photo {photo_id}: {elapsed:.2f}s"
        if input_tokens is not None or output_tokens is not None:
            log_message += f", tokens in={input_tokens or 0}, out={output_tokens or 0}"
        if est_cost is not None:
            log_message += f", est_cost=${est_cost:.4f}"
        logging.info(log_message)

        if not parsed.get("annotation_has_building") or parsed.get("annotation_location_type") != "outdoor":
            parsed["annotation_has_synagogue"] = False
            parsed["annotation_has_feor"] = False
            parsed["annotation_has_other_building"] = False
        elif bundle.building_focus in {"synagogue", "feor"}:
            verify_result = self._verify_special_building(
                bundle.image_for_model,
                bundle.building_focus,
                bundle.poi_label,
                photo_id,
            )
            if verify_result is not None:
                if bundle.building_focus == "synagogue":
                    parsed["annotation_has_synagogue"] = verify_result
                    if verify_result:
                        parsed["annotation_has_other_building"] = bool(
                            parsed.get("annotation_has_other_building")
                        )
                elif bundle.building_focus == "feor":
                    parsed["annotation_has_feor"] = verify_result
                    if verify_result:
                        parsed["annotation_has_other_building"] = bool(
                            parsed.get("annotation_has_other_building")
                        )

        parsed["model_version"] = self.model_name
        parsed["model_timestamp"] = utc_now_iso()
        return parsed

    def _verify_special_building(
        self,
        image_url: Optional[str],
        building_focus: str,
        poi_label: str,
        photo_id: Any,
    ) -> Optional[bool]:
        if not image_url:
            return None
        references = self.reference_map.get(building_focus)
        if not references:
            return None

        content = build_building_verification_content(
            image_url, building_focus, poi_label, references
        )
        if content is None:
            return None

        logging.debug(
            "Building verification request (photo=%s, focus=%s, refs=%d): %s",
            photo_id,
            building_focus,
            len(references),
            json.dumps(content, ensure_ascii=False),
        )

        start_time = time.perf_counter()
        try:
            response = self.client.responses.parse(
                model=self.model_name,
                input=[
                    {
                        "role": "user",
                        "content": content,
                    }
                ],
                text_format=BuildingVerificationModel,
            )
            parsed = response.output_parsed
            elapsed = time.perf_counter() - start_time
            usage = getattr(response, "usage", None)
            input_tokens = getattr(usage, "input_tokens", None) if usage else None
            if input_tokens is None and usage:
                input_tokens = getattr(usage, "prompt_tokens", None)
            output_tokens = getattr(usage, "output_tokens", None) if usage else None
            if output_tokens is None and usage:
                output_tokens = getattr(usage, "completion_tokens", None)
            est_cost = estimate_usage_cost(
                self.model_name, input_tokens, output_tokens
            )
            log_msg = (
                f"OpenAI {self.model_name} building-check ({building_focus}) photo {photo_id}: "
                f"{elapsed:.2f}s"
            )
            if input_tokens is not None or output_tokens is not None:
                log_msg += f", tokens in={input_tokens or 0}, out={output_tokens or 0}"
            if est_cost is not None:
                log_msg += f", est_cost=${est_cost:.4f}"
            logging.info(log_msg)
            logging.info(
                "Building verification response (photo=%s, focus=%s): %s",
                photo_id,
                building_focus,
                json.dumps(parsed.model_dump(), ensure_ascii=False),
            )
            return bool(parsed.matches_reference)
        except Exception as exc:  # pragma: no cover - network errors
            logging.warning(
                "Failed building verification for photo %s (%s): %s",
                photo_id,
                building_focus,
                exc,
            )
            return None


def load_reference_image(source: Optional[str]) -> Optional[Tuple[str, Dict[str, str]]]:
    if not source:
        return None
    if source.startswith("http://") or source.startswith("https://"):
        return (source, {"type": "input_image", "image_url": source})
    path = Path(source)
    if not path.exists():
        logging.warning("Reference image %s not found; skipping.", source)
        return None
    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    return (str(path), {"type": "input_image", "image_base64": encoded})


def _collect_reference_entries(
    sources: Optional[Sequence[str]],
    kind: str,
    collector: List[Tuple[str, str, Dict[str, str]]],
) -> None:
    if not sources:
        return
    for source in sources:
        reference = load_reference_image(source)
        if reference:
            collector.append((kind, reference[0], reference[1]))


def gather_reference_images(
    synagogue_sources: Optional[Sequence[str]], feor_sources: Optional[Sequence[str]]
) -> List[Tuple[str, str, Dict[str, str]]]:
    references: List[Tuple[str, str, Dict[str, str]]] = []
    _collect_reference_entries(synagogue_sources, "synagogue", references)
    _collect_reference_entries(feor_sources, "feor", references)
    return references


# ---------------------------------------------------------------------------
# OpenAI Batch helpers
# ---------------------------------------------------------------------------


class OpenAIBatchRequestBuilder:
    def __init__(
        self,
        model_name: str,
        reference_images: Sequence[Tuple[str, str, Dict[str, str]]] = (),
        enable_building_verification: bool = False,
        building_flag_column: str = "annotation_has_building",
        only_building_verification: bool = False,
    ):
        self.model_name = model_name
        self.reference_map: Dict[str, List[Tuple[str, Dict[str, str]]]] = {}
        for kind, label, payload in reference_images:
            self.reference_map.setdefault(kind, []).append((label, payload))
        self.annotation_format = json_schema_response_format(PhotoAnnotationModel)
        self.verification_format = json_schema_response_format(
            BuildingVerificationModel
        )
        self.only_building_verification = only_building_verification
        self.enable_building_verification = (
            enable_building_verification or only_building_verification
        )
        self.building_flag_column = building_flag_column
        self._missing_reference_focus_warned: Set[str] = set()

    def build_requests(
        self, df: pd.DataFrame
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]], List[str]]:
        requests: List[Dict[str, Any]] = []
        manifest_photos: Dict[str, Dict[str, Any]] = {}
        ordered_photo_keys: List[str] = []

        for _, row in df.iterrows():
            record = row.to_dict()
            photo_key = record.get("_photo_key") or build_photo_key(
                record.get("owner_id"), record.get("photo_id")
            )
            ordered_photo_keys.append(photo_key)
            bundle = build_annotation_prompt_bundle(record)
            annotation_custom_id: Optional[str] = None
            if not self.only_building_verification:
                annotation_custom_id = f"annotation:{photo_key}"
                requests.append(
                    {
                        "custom_id": annotation_custom_id,
                        "method": "POST",
                        "url": "/v1/responses",
                        "body": {
                            "model": self.model_name,
                            "input": [{"role": "user", "content": bundle.content}],
                            "text": {"format": self.annotation_format},
                        },
                    }
                )

            verification_ids: List[str] = []
            if self.enable_building_verification:
                verification_id = self._schedule_building_verification(
                    record, bundle, photo_key, requests
                )
                if verification_id:
                    verification_ids.append(verification_id)

            manifest_photos[photo_key] = {
                "annotation_custom_id": annotation_custom_id,
                "verification_custom_ids": verification_ids,
                "building_focus": bundle.building_focus,
                "poi_label": bundle.poi_label,
                "photo_key": photo_key,
                "photo_id": record.get("photo_id"),
                "owner_id": record.get("owner_id"),
            }

        return requests, manifest_photos, ordered_photo_keys

    def _schedule_building_verification(
        self,
        record: Dict[str, Any],
        bundle: AnnotationPromptBundle,
        photo_key: str,
        requests: List[Dict[str, Any]],
    ) -> Optional[str]:
        if not self.enable_building_verification:
            return None
        if not bundle.building_focus:
            return None
        if not self._row_has_building_flag(record):
            return None
        references = self.reference_map.get(bundle.building_focus)
        if not references:
            if bundle.building_focus not in self._missing_reference_focus_warned:
                logging.warning(
                    "No reference images available for '%s'; skipping verification for %s.",
                    bundle.building_focus,
                    photo_key,
                )
                self._missing_reference_focus_warned.add(bundle.building_focus)
            return None
        content = build_building_verification_content(
            bundle.image_for_model,
            bundle.building_focus,
            bundle.poi_label,
            references,
        )
        if content is None:
            return None
        verification_custom_id = f"verification:{bundle.building_focus}:{photo_key}"
        requests.append(
            {
                "custom_id": verification_custom_id,
                "method": "POST",
                "url": "/v1/responses",
                "body": {
                    "model": self.model_name,
                    "input": [{"role": "user", "content": content}],
                    "text": {"format": self.verification_format},
                },
            }
        )
        return verification_custom_id

    def _row_has_building_flag(self, record: Dict[str, Any]) -> bool:
        columns = [self.building_flag_column]
        if self.building_flag_column != "annotation_has_building":
            columns.append("annotation_has_building")
        for column in columns:
            if column not in record:
                continue
            if coerce_bool(record.get(column)):
                return True
        return False


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"JSONL file not found: {path}")
    entries: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for idx, line in enumerate(handle, start=1):
            content = line.strip()
            if not content:
                continue
            try:
                entries.append(json.loads(content))
            except json.JSONDecodeError as exc:
                logging.warning(
                    "Skipping malformed JSON at %s line %d: %s", path, idx, exc
                )
    return entries


def parse_metadata_args(pairs: Sequence[str]) -> Dict[str, str]:
    metadata: Dict[str, str] = {}
    for raw in pairs:
        if "=" not in raw:
            logging.warning(
                "Ignoring metadata entry '%s'; expected KEY=VALUE format.", raw
            )
            continue
        key, value = raw.split("=", 1)
        key_clean = key.strip()
        if not key_clean:
            logging.warning("Skipping metadata entry with empty key: %s", raw)
            continue
        metadata[key_clean] = value.strip()
    return metadata


def build_openai_client(api_key: Optional[str], base_url: Optional[str]):
    if OpenAI is None:
        raise RuntimeError("openai package is required but not installed.")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for OpenAI Batch commands.")
    return OpenAI(api_key=api_key, base_url=base_url)


def extract_response_text(body: Dict[str, Any]) -> Optional[str]:
    output_items = body.get("output") or []
    collected: List[str] = []
    for output in output_items:
        content_items = output.get("content") or []
        for item in content_items:
            item_type = item.get("type")
            if item_type in {"output_text", "text"}:
                text_value = item.get("text")
                if isinstance(text_value, list):
                    collected.append(
                        "".join(part.get("text", "") for part in text_value)
                    )
                elif isinstance(text_value, str):
                    collected.append(text_value)
    if collected:
        return "".join(collected).strip()
    fallback = body.get("output_text")
    if isinstance(fallback, str):
        return fallback.strip()
    return None


def parse_batch_response_json(
    entry: Dict[str, Any], label: str
) -> Optional[Dict[str, Any]]:
    response = entry.get("response") or {}
    body = response.get("body")
    if not body:
        logging.warning("Batch entry %s missing body.", label)
        return None
    text = extract_response_text(body)
    if not text:
        logging.warning("Batch entry %s missing textual output.", label)
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        logging.error("Failed to parse JSON payload for %s: %s", label, exc)
        return None


def extract_usage_tokens(
    entry: Dict[str, Any]
) -> Tuple[Optional[int], Optional[int]]:
    response = entry.get("response") or {}
    body = response.get("body") or {}
    usage = body.get("usage") or {}
    input_tokens = usage.get("input_tokens", usage.get("prompt_tokens"))
    output_tokens = usage.get("output_tokens", usage.get("completion_tokens"))
    return input_tokens, output_tokens


# ---------------------------------------------------------------------------
# Annotation orchestration


def _load_cached_annotation(cache_path: Path) -> Optional[Dict[str, Any]]:
    if not cache_path.exists():
        return None
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logging.warning("Cache file %s is corrupted.", cache_path)
        return None


def annotate_rows(
    df: pd.DataFrame,
    model_client: Optional[MultimodalModelClient],
    cache_dir: Path,
    resume: bool,
    checkpoint: AnnotationCheckpoint,
    checkpoint_interval: int,
) -> Dict[str, Dict[str, Any]]:
    ensure_directory(cache_dir)
    annotations: Dict[str, Dict[str, Any]] = {}
    processed_since_save = 0

    for _, row in df.iterrows():
        row_dict = row.to_dict()
        photo_id_value = row_dict.get("photo_id")
        photo_id_display = row_dict.get("photo_id")
        owner_id_value = row_dict.get("owner_id")
        photo_key = row_dict.get("_photo_key") or build_photo_key(
            owner_id_value, photo_id_value
        )
        cache_path = cache_dir / f"{photo_key}.json"

        if resume:
            cached = None
            if checkpoint.should_skip(photo_key) or cache_path.exists():
                cached = _load_cached_annotation(cache_path)
            if cached is not None:
                annotations[photo_key] = cached
                checkpoint.mark_complete(photo_key)
                continue
            if checkpoint.should_skip(photo_key):
                logging.warning(
                    "Checkpoint referenced %s but cache missing; re-running.", photo_key
                )

        if model_client is None:
            annotation = default_annotation()
        else:
            try:
                annotation = model_client.annotate(row_dict)
            except Exception as exc:  # pragma: no cover - network errors
                logging.error("Model failed for photo %s: %s", photo_id_display, exc)
                annotation = default_annotation()

        annotations[photo_key] = annotation
        checkpoint.mark_complete(photo_key)
        processed_since_save += 1

        cache_path.write_text(
            json.dumps(annotation, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        if processed_since_save >= checkpoint_interval:
            checkpoint.save()
            processed_since_save = 0

    if processed_since_save:
        checkpoint.save()

    return annotations


def merge_annotations(
    df: pd.DataFrame, annotations: Dict[str, Dict[str, Any]]
) -> pd.DataFrame:
    merged_records: List[Dict[str, Any]] = []

    for _, row in df.iterrows():
        record = row.to_dict()
        photo_key = record.get("_photo_key") or build_photo_key(
            record.get("owner_id"), record.get("photo_id")
        )
        annotation = annotations.get(photo_key, default_annotation())
        record.update(annotation)
        merged_records.append(record)

    merged = pd.DataFrame(merged_records)
    missing_cols = [col for col in CSV_COLUMNS if col not in merged.columns]
    for col in missing_cols:
        merged[col] = None
    merged = merged[CSV_COLUMNS]
    return merged


def prepare_annotation_dataframe(
    input_csv: Path,
    vk_token: Optional[str],
    skip_user_fetch: bool,
    cache_dir: Path,
    limit: Optional[int],
    shuffle: bool,
    subset_photo_ids: Optional[List[str]] = None,
    subset_row_keys: Optional[List[str]] = None,
) -> pd.DataFrame:
    df = load_csv(input_csv)
    df = filter_visible_rows(df)

    subset_order: Dict[str, int] = {}
    subset_key_order: Dict[str, int] = {}
    if subset_photo_ids:
        subset_strings = [str(pid) for pid in subset_photo_ids]
        subset_lookup = set(subset_strings)
        df = df[df["photo_id"].astype(str).isin(subset_lookup)].copy()
        subset_order = {photo_id: idx for idx, photo_id in enumerate(subset_strings)}
    subset_key_lookup: Optional[Set[str]] = None
    if subset_row_keys:
        subset_key_strings = [str(key) for key in subset_row_keys]
        subset_key_lookup = set(subset_key_strings)
        subset_key_order = {key: idx for idx, key in enumerate(subset_key_strings)}

    if shuffle:
        df = df.sample(frac=1.0, random_state=41).reset_index(drop=True)
    if limit:
        df = df.head(limit)

    related_links = normalize_related_links(df)
    if skip_user_fetch:
        user_info = {}
    else:
        fetcher = VKUserMetadataFetcher(
            token=vk_token,
            cache_file=cache_dir / "users.json",
        )
        user_info = fetcher.enrich(df["user_id"].unique())

    enriched = restructure_dataframe(df, related_links, user_info)
    if subset_photo_ids:
        order_series = enriched["photo_id"].astype(str).map(subset_order)
        enriched = (
            enriched.assign(_order=order_series)
            .sort_values("_order", na_position="last")
            .drop(columns="_order")
        )
    if subset_key_lookup:
        if "_photo_key" not in enriched.columns:
            enriched["_photo_key"] = enriched.apply(
                lambda r: build_photo_key(r.get("owner_id"), r.get("photo_id")), axis=1
            )
        enriched = enriched[enriched["_photo_key"].isin(subset_key_lookup)].copy()
        order_series_keys = enriched["_photo_key"].map(subset_key_order)
        enriched = (
            enriched.assign(_order_key=order_series_keys)
            .sort_values("_order_key", na_position="last")
            .drop(columns="_order_key")
        )
    return enriched.reset_index(drop=True)


def restructure_dataframe(
    df: pd.DataFrame,
    related_links: Dict[str, List[str]],
    user_info: Dict[str, Dict[str, Any]],
    poi_lookup: Optional[Dict[str, str]] = None,
) -> pd.DataFrame:
    records: List[Dict[str, Any]] = []

    for _, row in df.iterrows():
        record = row.to_dict()
        photo_id = str(record.get("photo_id"))
        post_id = record.get("post_id")
        owner_id = record.get("owner_id")

        record["post_url"] = build_post_url(owner_id, post_id)
        if post_id and str(post_id) in related_links:
            related_urls = [url for url in related_links[str(post_id)] if url != record["image_url"]]
            record["related_photo_urls"] = ";".join(related_urls)
        else:
            record["related_photo_urls"] = ""

        text_value = ensure_text(record.get("text"))
        record["hashtags"] = ";".join(extract_hashtags(text_value))
        record["post_text"] = text_value.strip()

        user_id = record.get("user_id")
        if not pd.isna(user_id):
            user_meta = user_info.get(str(int(user_id)), {})
        else:
            user_meta = {}
        record["user_gender"] = user_meta.get("user_gender")
        record["user_age"] = user_meta.get("user_age")
        record["user_city"] = user_meta.get("user_city")
        record["user_city_id"] = user_meta.get("user_city_id")
        record["user_kind"] = user_meta.get("user_kind")

        if poi_lookup and record.get("poi_name") in poi_lookup:
            record["poi_name"] = poi_lookup[record["poi_name"]]

        record["_photo_key"] = build_photo_key(
            record.get("owner_id"), record.get("photo_id")
        )
        records.append(record)

    enriched = pd.DataFrame(records)
    return enriched


# ---------------------------------------------------------------------------
# Dataset filtering
# ---------------------------------------------------------------------------


def filter_visible_rows(df: pd.DataFrame) -> pd.DataFrame:
    column = "inside_poi_area"
    if column not in df.columns:
        logging.warning(
            "Column '%s' not found; cannot filter rows by POI visibility.", column
        )
        return df

    series = df[column]
    if is_bool_dtype(series):
        mask = series.fillna(False)
    else:
        normalized = (
            series.fillna("")
            .astype(str)
            .str.strip()
            .str.lower()
        )
        mask = normalized.isin({"true", "1", "yes"})

    mask = mask.astype(bool)
    filtered = df[mask].copy()
    dropped = len(df) - len(filtered)
    if dropped > 0:
        logging.info(
            "Skipped %d rows outside POI visibility (%s column).", dropped, column
        )
    if filtered.empty:
        logging.warning(
            "After filtering by %s, no rows remain. Check the input dataset.", column
        )
    return filtered


def filter_rows_missing_annotations(
    df: pd.DataFrame, column: str = "annotation_text_description"
) -> pd.DataFrame:
    if column not in df.columns:
        logging.info(
            "Column '%s' absent in dataset; skipping missing-annotation filter.", column
        )
        return df
    normalized = (
        df[column]
        .fillna("")
        .astype(str)
        .str.strip()
    )
    mask = normalized == ""
    filtered = df[mask].copy()
    dropped = len(df) - len(filtered)
    logging.info(
        "Selected %d/%d rows with empty '%s' values.",
        len(filtered),
        len(df),
        column,
    )
    if filtered.empty:
        logging.warning(
            "No rows missing '%s' remain after filtering; nothing to process.", column
        )
    return filtered


def filter_rows_by_flag(df: pd.DataFrame, column: str) -> pd.DataFrame:
    if column not in df.columns:
        logging.warning(
            "Column '%s' not found; skipping flag-based filtering.", column
        )
        return df
    mask = df[column].apply(coerce_bool)
    filtered = df[mask].copy()
    dropped = len(df) - len(filtered)
    logging.info(
        "Filtered to %d/%d rows where '%s' is truthy.",
        len(filtered),
        len(df),
        column,
    )
    if filtered.empty:
        logging.warning(
            "No rows matched truthy '%s' after filtering; nothing to process.", column
        )
    return filtered


# ---------------------------------------------------------------------------
# Golden set helpers


def create_golden_draft(enriched_csv: Path, output_dir: Path, sample_size: int, seed: int, strategy: str) -> Path:
    df = load_csv(enriched_csv)
    df = filter_visible_rows(df)
    if strategy == "recent" and "date_human" in df.columns:
        df = df.sort_values("date_human", ascending=False)
    elif strategy == "unique_by_user":
        df = df.groupby("user_id").sample(n=1, random_state=seed)
    else:
        df = df.sample(frac=1.0, random_state=seed)

    subset = df.head(sample_size).copy()
    for field in ANNOTATION_FIELDS:
        subset[f"human_{field}"] = ""

    ensure_directory(output_dir)
    draft_path = output_dir / f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_draft.csv"
    subset.to_csv(draft_path, index=False)
    logging.info("Golden draft saved to %s", draft_path)
    return draft_path


def apply_reviewed_golden(reviewed_csv: Path, golden_csv: Path) -> None:
    df = load_csv(reviewed_csv)
    human_cols = [col for col in df.columns if col.startswith("human_")]
    if not human_cols:
        raise ValueError("No human_* columns found in reviewed file.")

    merged_records = []
    for _, row in df.iterrows():
        record = row.to_dict()
        for field in ANNOTATION_FIELDS:
            human_value = record.get(f"human_{field}")
            if human_value not in (None, "", " "):
                record[field] = human_value
        merged_records.append({col: record.get(col) for col in CSV_COLUMNS if col in record})

    ensure_directory(golden_csv.parent)
    pd.DataFrame(merged_records).to_csv(golden_csv, index=False)
    logging.info("Golden labels saved to %s", golden_csv)


def evaluate_predictions(predictions: Path, golden_csv: Path, report_json: Path) -> Dict[str, Any]:
    pred_df = load_csv(predictions)
    golden_df = load_csv(golden_csv)

    common = pd.merge(
        golden_df,
        pred_df,
        on="photo_id",
        suffixes=("_golden", "_pred"),
    )

    metrics: Dict[str, Any] = {"total_overlap": len(common)}
    if len(common) == 0:
        logging.warning("No overlapping photo_id records between predictions and golden set.")
        report_json.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
        return metrics

    boolean_fields = [
        "annotation_is_advertisement",
        "annotation_has_building",
        "annotation_has_synagogue",
        "annotation_has_feor",
        "annotation_has_other_building",
    ]

    for field in boolean_fields:
        g = common[f"{field}_golden"].astype(str)
        p = common[f"{field}_pred"].astype(str)
        metrics[field] = float((g == p).mean())

    metrics["annotation_photo_type"] = float(
        (
            common["annotation_photo_type_golden"]
            == common["annotation_photo_type_pred"]
        ).mean()
    )

    ensure_directory(report_json.parent)
    report_json.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    logging.info("Evaluation metrics written to %s", report_json)
    return metrics


# ---------------------------------------------------------------------------
# Main flow


def run_annotate(args: argparse.Namespace) -> None:
    enriched = prepare_annotation_dataframe(
        input_csv=args.input_csv,
        vk_token=args.vk_token,
        skip_user_fetch=args.skip_user_fetch,
        cache_dir=args.cache_dir,
        limit=args.limit,
        shuffle=args.shuffle,
        subset_photo_ids=args.only_photo_ids,
    )

    model_client: Optional[MultimodalModelClient] = None
    if args.model_provider == "openai":
        references = gather_reference_images(
            args.reference_synagogue, args.reference_feor
        )
        model_client = OpenAIMultimodalClient(
            model_name=args.model_name,
            api_key=args.openai_api_key,
            base_url=args.openai_base_url,
            reference_images=references,
        )
    elif args.model_provider == "none":
        logging.info("Skipping multimodal annotations (model-provider=none).")

    model_cache_dir = args.cache_dir / "model_responses"
    checkpoint = AnnotationCheckpoint(args.checkpoint_file)
    if args.resume:
        checkpoint.load()
    else:
        checkpoint.reset_file()

    annotations = annotate_rows(
        enriched,
        model_client=model_client,
        cache_dir=model_cache_dir,
        resume=args.resume,
        checkpoint=checkpoint,
        checkpoint_interval=args.checkpoint_interval,
    )
    checkpoint.reset_file()

    merged = merge_annotations(enriched, annotations)
    merged.to_csv(args.output_csv, index=False)
    logging.info("Enriched CSV saved to %s", args.output_csv)

    # Also dump model responses in JSON Lines for auditing
    with args.model_responses.open("w", encoding="utf-8") as f:
        for _, row in enriched.iterrows():
            row_dict = row.to_dict()
            photo_key = row_dict.get("_photo_key") or build_photo_key(
                row_dict.get("owner_id"), row_dict.get("photo_id")
            )
            payload = annotations.get(photo_key)
            if payload is None:
                continue
            entry = {
                "photo_key": photo_key,
                "photo_id": row_dict.get("photo_id"),
                "owner_id": row_dict.get("owner_id"),
                **payload,
            }
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    logging.info("Model responses exported to %s", args.model_responses)

    if args.only_photo_ids:
        requested = {str(pid) for pid in args.only_photo_ids}
        matches = enriched[enriched["photo_id"].astype(str).isin(requested)]
        if matches.empty:
            logging.warning(
                "Requested photo_ids %s not found in the processed dataset.",
                ", ".join(sorted(requested)),
            )
        for _, row in matches.iterrows():
            row_dict = row.to_dict()
            photo_key = row_dict.get("_photo_key") or build_photo_key(
                row_dict.get("owner_id"), row_dict.get("photo_id")
            )
            payload = annotations.get(photo_key)
            if payload is None:
                logging.warning(
                    "Requested photo_id %s (owner %s) had no annotation payload.",
                    row_dict.get("photo_id"),
                    row_dict.get("owner_id"),
                )
                continue
            logging.info(
                "Annotation for photo_id %s (owner %s):\n%s",
                row_dict.get("photo_id"),
                row_dict.get("owner_id"),
                json.dumps(payload, ensure_ascii=False, indent=2),
            )


def run_openai_batch_prepare(args: argparse.Namespace) -> None:
    enriched = prepare_annotation_dataframe(
        input_csv=args.input_csv,
        vk_token=args.vk_token,
        skip_user_fetch=args.skip_user_fetch,
        cache_dir=args.cache_dir,
        limit=args.limit,
        shuffle=args.shuffle,
        subset_row_keys=None,
    )
    if args.only_missing_annotations:
        enriched = filter_rows_missing_annotations(
            enriched, args.missing_annotation_column
        )
    if args.only_building_flagged:
        enriched = filter_rows_by_flag(enriched, args.building_flag_column)
    references = gather_reference_images(
        args.reference_synagogue, args.reference_feor
    )
    builder = OpenAIBatchRequestBuilder(
        args.model_name,
        references,
        enable_building_verification=args.enable_building_verification,
        building_flag_column=args.building_flag_column,
        only_building_verification=args.only_building_verification,
    )
    requests, manifest_photos, photo_keys = builder.build_requests(enriched)

    ensure_directory(args.batch_input.parent)
    with args.batch_input.open("w", encoding="utf-8") as handle:
        for record in requests:
            handle.write(json.dumps(record, ensure_ascii=False))
            handle.write("\n")

    manifest = {
        "version": 1,
        "generated_at": utc_now_iso(),
        "model_name": args.model_name,
        "dataset": {
            "input_csv": str(args.input_csv),
            "limit": args.limit,
            "shuffle": args.shuffle,
            "skip_user_fetch": args.skip_user_fetch,
            "row_count": len(enriched),
        },
        "photo_keys": photo_keys,
        "photos": manifest_photos,
    }
    ensure_directory(args.manifest.parent)
    args.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    logging.info(
        "Prepared %d batch requests across %d photos. Input saved to %s; manifest saved to %s.",
        len(requests),
        len(photo_keys),
        args.batch_input,
        args.manifest,
    )


def run_openai_batch_apply(args: argparse.Namespace) -> None:
    if not args.manifest.exists():
        raise FileNotFoundError(f"Manifest not found: {args.manifest}")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    manifest_photos: Dict[str, Dict[str, Any]] = manifest.get("photos", {})
    photo_keys: List[str] = manifest.get("photo_keys") or list(manifest_photos.keys())
    if not photo_keys:
        raise RuntimeError("Manifest contains no photo entries to apply.")

    enriched = prepare_annotation_dataframe(
        input_csv=args.input_csv,
        vk_token=args.vk_token,
        skip_user_fetch=args.skip_user_fetch,
        cache_dir=args.cache_dir,
        limit=None,
        shuffle=False,
        subset_row_keys=photo_keys,
    )

    if "_photo_key" not in enriched.columns:
        enriched["_photo_key"] = enriched.apply(
            lambda r: build_photo_key(r.get("owner_id"), r.get("photo_id")), axis=1
        )
    enriched_keys = set(enriched["_photo_key"].astype(str))
    missing_keys = [key for key in photo_keys if key not in enriched_keys]
    if missing_keys:
        logging.warning(
            "Manifest references %d photos missing from the current dataset. They will be skipped.",
            len(missing_keys),
        )

    response_entries = load_jsonl(args.batch_output)
    response_map: Dict[str, Dict[str, Any]] = {
        entry["custom_id"]: entry
        for entry in response_entries
        if isinstance(entry, dict) and entry.get("custom_id")
    }
    error_map: Dict[str, Dict[str, Any]] = {}
    if args.batch_errors:
        for entry in load_jsonl(args.batch_errors):
            custom_id = entry.get("custom_id")
            if custom_id:
                error_map[custom_id] = entry

    annotations: Dict[str, Dict[str, Any]] = {}
    model_name = manifest.get("model_name", "unknown")

    for photo_key in photo_keys:
        meta = manifest_photos.get(photo_key, {})
        annotation_custom_id = meta.get("annotation_custom_id")
        annotation_data = default_annotation()
        parsed = None
        if annotation_custom_id and annotation_custom_id in response_map:
            parsed = parse_batch_response_json(
                response_map[annotation_custom_id], annotation_custom_id
            )
            input_tokens, output_tokens = extract_usage_tokens(
                response_map[annotation_custom_id]
            )
            est_cost = estimate_usage_cost(model_name, input_tokens, output_tokens)
            log_msg = (
                f"Batch annotation {annotation_custom_id} photo_key {photo_key}: "
                f"tokens in={input_tokens or 0}, out={output_tokens or 0}"
            )
            if est_cost is not None:
                log_msg += f", est_cost=${est_cost:.4f}"
            logging.info(log_msg)
        elif annotation_custom_id and annotation_custom_id in error_map:
            logging.error(
                "Annotation request %s failed: %s",
                annotation_custom_id,
                error_map[annotation_custom_id].get("error"),
            )
        else:
            logging.warning(
                "No annotation result found for key %s (custom_id=%s).",
                photo_key,
                annotation_custom_id,
            )

        if parsed:
            annotation_data.update(parsed)
        annotation_data["model_version"] = model_name
        annotation_data["model_timestamp"] = utc_now_iso()

        building_focus = meta.get("building_focus")
        if (
            not annotation_data.get("annotation_has_building")
            or annotation_data.get("annotation_location_type") != "outdoor"
        ):
            annotation_data["annotation_has_synagogue"] = False
            annotation_data["annotation_has_feor"] = False
            annotation_data["annotation_has_other_building"] = False
        elif building_focus in {"synagogue", "feor"}:
            verification_ids: List[str] = []
            if isinstance(meta.get("verification_custom_ids"), list):
                verification_ids.extend(meta.get("verification_custom_ids"))

            verification_result: Optional[bool] = None
            for vid in verification_ids:
                if vid in response_map:
                    verification_payload = parse_batch_response_json(
                        response_map[vid], vid
                    )
                    if verification_payload is not None:
                        matches = bool(verification_payload.get("matches_reference"))
                        verification_result = (
                            matches
                            if verification_result is None
                            else verification_result or matches
                        )
                        logging.debug(
                            "Batch verification response %s (photo_key=%s): %s",
                            vid,
                            photo_key,
                            json.dumps(verification_payload, ensure_ascii=False),
                        )
                        if matches:
                            break
                elif vid in error_map:
                    logging.warning(
                        "Verification request %s failed: %s",
                        vid,
                        error_map[vid].get("error"),
                    )
                else:
                    logging.warning(
                        "Verification result %s missing in batch outputs.", vid
                    )

            if verification_result is not None:
                if building_focus == "synagogue":
                    annotation_data["annotation_has_synagogue"] = verification_result
                    if verification_result:
                        annotation_data["annotation_has_other_building"] = bool(
                            annotation_data.get("annotation_has_other_building")
                        )
                elif building_focus == "feor":
                    annotation_data["annotation_has_feor"] = verification_result
                    if verification_result:
                        annotation_data["annotation_has_other_building"] = bool(
                            annotation_data.get("annotation_has_other_building")
                        )

        annotations[photo_key] = annotation_data

    merged = merge_annotations(enriched, annotations)
    merged.to_csv(args.output_csv, index=False)
    logging.info("Batch output merged into %s", args.output_csv)

    with args.model_responses.open("w", encoding="utf-8") as handle:
        for _, row in enriched.iterrows():
            row_dict = row.to_dict()
            row_key = row_dict.get("_photo_key") or build_photo_key(
                row_dict.get("owner_id"), row_dict.get("photo_id")
            )
            payload = annotations.get(row_key)
            if payload is None:
                continue
            entry = {
                "photo_key": row_key,
                "photo_id": row_dict.get("photo_id"),
                "owner_id": row_dict.get("owner_id"),
                **payload,
            }
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    logging.info("Flattened batch responses written to %s", args.model_responses)


def run_openai_batch_upload(args: argparse.Namespace) -> None:
    if not args.file_path.exists():
        raise FileNotFoundError(f"Batch input file not found: {args.file_path}")
    client = build_openai_client(args.openai_api_key, args.openai_base_url)
    with args.file_path.open("rb") as handle:
        file_obj = client.files.create(file=handle, purpose="batch")
    size_bytes = args.file_path.stat().st_size
    logging.info(
        "Uploaded %s (%d bytes). File ID: %s",
        args.file_path,
        size_bytes,
        file_obj.id,
    )


def run_openai_batch_create(args: argparse.Namespace) -> None:
    client = build_openai_client(args.openai_api_key, args.openai_base_url)
    metadata = parse_metadata_args(args.metadata)
    batch = client.batches.create(
        input_file_id=args.input_file_id,
        endpoint=args.endpoint,
        completion_window=args.completion_window,
        metadata=metadata or None,
    )
    logging.info(
        "Created batch %s (status=%s). Output file: %s, error file: %s",
        batch.id,
        batch.status,
        getattr(batch, "output_file_id", None),
        getattr(batch, "error_file_id", None),
    )


def run_openai_batch_status(args: argparse.Namespace) -> None:
    client = build_openai_client(args.openai_api_key, args.openai_base_url)
    batch = client.batches.retrieve(args.batch_id)
    counts = getattr(batch, "request_counts", None)
    total = getattr(counts, "total", None) if counts else None
    completed = getattr(counts, "completed", None) if counts else None
    failed = getattr(counts, "failed", None) if counts else None
    logging.info(
        "Batch %s status=%s total=%s completed=%s failed=%s output=%s error=%s",
        batch.id,
        batch.status,
        total,
        completed,
        failed,
        getattr(batch, "output_file_id", None),
        getattr(batch, "error_file_id", None),
    )


def run_openai_batch_results(args: argparse.Namespace) -> None:
    client = build_openai_client(args.openai_api_key, args.openai_base_url)
    ensure_directory(args.output.parent)
    response = client.files.content(args.file_id)
    response.write_to_file(str(args.output))
    logging.info("Downloaded file %s to %s", args.file_id, args.output)


def run_openai_batch_cancel(args: argparse.Namespace) -> None:
    client = build_openai_client(args.openai_api_key, args.openai_base_url)
    batch = client.batches.cancel(args.batch_id)
    logging.info(
        "Cancellation requested for batch %s. New status=%s",
        batch.id,
        batch.status,
    )


def run_openai_batch_list(args: argparse.Namespace) -> None:
    client = build_openai_client(args.openai_api_key, args.openai_base_url)
    listing = client.batches.list(limit=args.limit, after=args.after)
    data = getattr(listing, "data", listing)
    for batch in data:
        counts = getattr(batch, "request_counts", None)
        total = getattr(counts, "total", None) if counts else None
        completed = getattr(counts, "completed", None) if counts else None
        failed = getattr(counts, "failed", None) if counts else None
        logging.info(
            "Batch %s status=%s total=%s completed=%s failed=%s output=%s error=%s",
            batch.id,
            batch.status,
            total,
            completed,
            failed,
            getattr(batch, "output_file_id", None),
            getattr(batch, "error_file_id", None),
        )


def run_openai_batch_sequential(args: argparse.Namespace) -> None:
    enriched = prepare_annotation_dataframe(
        input_csv=args.input_csv,
        vk_token=args.vk_token,
        skip_user_fetch=args.skip_user_fetch,
        cache_dir=args.cache_dir,
        limit=args.limit,
        shuffle=args.shuffle,
    )
    if args.only_missing_annotations:
        enriched = filter_rows_missing_annotations(
            enriched, args.missing_annotation_column
        )
    if args.only_building_flagged:
        enriched = filter_rows_by_flag(enriched, args.building_flag_column)
    total_rows = len(enriched)
    if total_rows == 0:
        logging.warning("Dataset is empty after preprocessing; nothing to submit.")
        return

    references = gather_reference_images(
        args.reference_synagogue, args.reference_feor
    )
    builder = OpenAIBatchRequestBuilder(
        args.model_name,
        references,
        enable_building_verification=args.enable_building_verification,
        building_flag_column=args.building_flag_column,
        only_building_verification=args.only_building_verification,
    )
    client = build_openai_client(args.openai_api_key, args.openai_base_url)
    output_dir = ensure_directory(args.output_dir)
    chunk_size = max(1, int(args.chunk_size))
    poll_interval = max(5, int(args.poll_interval))
    metadata_base = parse_metadata_args(args.metadata)

    chunk_starts = range(0, total_rows, chunk_size)
    for chunk_index, chunk_start in enumerate(chunk_starts, start=1):
        if args.max_chunks is not None and chunk_index > args.max_chunks:
            logging.info(
                "Reached max-chunks limit (%s); stopping sequential submission.",
                args.max_chunks,
            )
            break

        chunk_end = min(chunk_start + chunk_size, total_rows)
        chunk_df = enriched.iloc[chunk_start:chunk_end].reset_index(drop=True)
        chunk_label = f"chunk_{chunk_index:04d}"
        logging.info(
            "Preparing %s covering rows %d-%d (total rows=%d).",
            chunk_label,
            chunk_start + 1,
            chunk_end,
            total_rows,
        )

        requests, manifest_photos, photo_keys = builder.build_requests(chunk_df)
        if not requests:
            logging.info("Chunk %s produced no requests; skipping.", chunk_label)
            continue

        input_path = output_dir / f"{chunk_label}_input.jsonl"
        manifest_path = output_dir / f"{chunk_label}_manifest.json"
        with input_path.open("w", encoding="utf-8") as handle:
            for record in requests:
                handle.write(json.dumps(record, ensure_ascii=False))
                handle.write("\n")

        manifest = {
            "version": 1,
            "generated_at": utc_now_iso(),
            "model_name": args.model_name,
            "chunk": {
                "label": chunk_label,
                "start_row": chunk_start,
                "end_row": chunk_end,
                "size": chunk_end - chunk_start,
            },
            "dataset": {
                "input_csv": str(args.input_csv),
                "limit": args.limit,
                "shuffle": args.shuffle,
                "skip_user_fetch": args.skip_user_fetch,
                "row_count": len(chunk_df),
            },
            "photo_keys": photo_keys,
            "photos": manifest_photos,
        }
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        logging.info(
            "Uploading %s (%d requests) to OpenAI Files API.",
            chunk_label,
            len(requests),
        )
        with input_path.open("rb") as handle:
            file_obj = client.files.create(file=handle, purpose="batch")

        metadata = dict(metadata_base)
        metadata.setdefault("chunk_label", chunk_label)
        metadata.setdefault("chunk_rows", str(chunk_end - chunk_start))
        batch = client.batches.create(
            input_file_id=file_obj.id,
            endpoint=args.endpoint,
            completion_window=args.completion_window,
            metadata=metadata or None,
        )
        logging.info(
            "Submitted %s as batch %s (status=%s). Waiting for completion before next chunk.",
            chunk_label,
            batch.id,
            batch.status,
        )

        terminal_states = {"completed", "failed", "cancelled", "canceled", "expired"}
        while batch.status not in terminal_states:
            logging.info(
                "Chunk %s batch %s still running (status=%s, total=%s, completed=%s, failed=%s).",
                chunk_label,
                batch.id,
                batch.status,
                getattr(getattr(batch, "request_counts", None), "total", None),
                getattr(getattr(batch, "request_counts", None), "completed", None),
                getattr(getattr(batch, "request_counts", None), "failed", None),
            )
            time.sleep(poll_interval)
            batch = client.batches.retrieve(batch.id)

        logging.info(
            "Chunk %s batch %s finished with status=%s.",
            chunk_label,
            batch.id,
            batch.status,
        )

        output_file_id = getattr(batch, "output_file_id", None)
        if output_file_id:
            dest = output_dir / f"{chunk_label}_output.jsonl"
            client.files.content(output_file_id).write_to_file(str(dest))
            logging.info("Downloaded output for %s to %s", chunk_label, dest)
        error_file_id = getattr(batch, "error_file_id", None)
        if error_file_id:
            dest = output_dir / f"{chunk_label}_errors.jsonl"
            client.files.content(error_file_id).write_to_file(str(dest))
            logging.info("Downloaded errors for %s to %s", chunk_label, dest)

        if batch.status != "completed":
            logging.error(
                "Chunk %s ended with status %s; stopping sequential submission.",
                chunk_label,
                batch.status,
            )
            break


def run_golden_draft(args: argparse.Namespace) -> None:
    path = create_golden_draft(
        enriched_csv=args.enriched_csv,
        output_dir=args.output_dir,
        sample_size=args.sample_size,
        seed=args.seed,
        strategy=args.strategy,
    )
    logging.info("Golden draft ready: %s", path)


def run_golden_apply(args: argparse.Namespace) -> None:
    apply_reviewed_golden(
        reviewed_csv=args.reviewed_csv,
        golden_csv=args.golden_csv,
    )


def run_evaluate(args: argparse.Namespace) -> None:
    metrics = evaluate_predictions(
        predictions=args.predictions,
        golden_csv=args.golden_csv,
        report_json=args.report_json,
    )
    logging.info("Evaluation metrics: %s", json.dumps(metrics, indent=2))


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    args = parse_args()

    if args.command == "annotate":
        run_annotate(args)
    elif args.command == "openai-batch":
        if args.batch_command == "prepare":
            run_openai_batch_prepare(args)
        elif args.batch_command == "apply":
            run_openai_batch_apply(args)
        elif args.batch_command == "upload":
            run_openai_batch_upload(args)
        elif args.batch_command == "create":
            run_openai_batch_create(args)
        elif args.batch_command == "status":
            run_openai_batch_status(args)
        elif args.batch_command == "results":
            run_openai_batch_results(args)
        elif args.batch_command == "cancel":
            run_openai_batch_cancel(args)
        elif args.batch_command == "list":
            run_openai_batch_list(args)
        elif args.batch_command == "sequential":
            run_openai_batch_sequential(args)
        else:  # pragma: no cover - defensive
            raise ValueError(f"Unknown batch sub-command: {args.batch_command}")
    elif args.command == "golden-draft":
        run_golden_draft(args)
    elif args.command == "golden-apply":
        run_golden_apply(args)
    elif args.command == "evaluate":
        run_evaluate(args)
    else:  # pragma: no cover - defensive
        raise ValueError(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()

