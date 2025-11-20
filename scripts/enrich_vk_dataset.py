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
from typing import Any, Dict, Iterable, List, Literal, Optional, Sequence, Set, Tuple
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import pandas as pd
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
    "annotation_situation_summary",
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
    annotation_situation_summary: str
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
    annotate.add_argument(
        "--input-csv",
        type=Path,
        default=Path("vk_photos_perm_historical.csv"),
        help="Source dataset produced by collect_vk_photos.py",
    )
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
        "--vk-token",
        type=str,
        default=os.environ.get("VK_TOKEN"),
        help="VK API token; falls back to VK_TOKEN env variable.",
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
    annotate.add_argument(
        "--openai-base-url",
        type=str,
        default=None,
        help="Custom OpenAI-compatible base URL (for local gateways).",
    )
    annotate.add_argument(
        "--openai-api-key",
        type=str,
        default=os.environ.get("OPENAI_API_KEY"),
        help="API key for OpenAI or compatible provider.",
    )
    annotate.add_argument(
        "--reference-synagogue",
        type=str,
        default=None,
        help="Optional URL or local path with canonical synagogue photo.",
    )
    annotate.add_argument(
        "--reference-feor",
        type=str,
        default=None,
        help="Optional URL or local path with canonical FEOR building photo.",
    )
    annotate.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process only the first N photos (useful for dry runs).",
    )
    annotate.add_argument(
        "--skip-user-fetch",
        action="store_true",
        help="Skip VK user metadata fetch (keeps user columns empty).",
    )
    annotate.add_argument(
        "--cache-dir",
        type=Path,
        default=DEFAULT_CACHE_DIR,
        help="Base directory for cached model responses and user data.",
    )
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
        "--shuffle",
        action="store_true",
        help="Randomize processing order to balance model load.",
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
        choices=["random", "recent"],
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
        "annotation_situation_summary": "",
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
        self.reference_map: Dict[str, Tuple[str, Dict[str, str]]] = {
            kind: (label, payload) for kind, label, payload in self.reference_images
        }

    def annotate(self, photo_row: Dict[str, Any]) -> Dict[str, Any]:
        poi_name = ensure_text(photo_row.get("poi_name"))
        building_focus = resolve_building_focus(poi_name)
        poi_label = poi_name or "неизвестный POI"

        prompt = textwrap.dedent(
            f"""
                Ты — специалист по описанию и классификации городских фотографий из социальных сетей.

                Твоя задача: проанализировать переданное изображение (и дополнительный текстовый контекст, если он есть) и вернуть JSON-объект с разметкой фотографии.
                Требования:
                1. Всегда отвечай строго ОДНИМ JSON-объектом, без поясняющего текста до или после него.
                2. Заполняй все поля JSON. Если информации недостаточно, используй значение "unknown" или пустую строку, но не пропускай ключ.
                3. Поле "photo_type" должно быть ровно ОДНИМ значением из допустимого списка:
                - "portrait" — одиночный портрет человека
                - "selfie" — селфи или кадр, где фотограф снимает себя
                - "group_portrait" — групповой портрет людей
                - "interior" — фото интерьера (помещение, зал, коридор, комната, и т.п.)
                - "cityscape" — городской пейзаж (улица, площадь, двор, вид города, открытое пространство)
                - "product" — фото товара или услуги (витрина с выкладкой, фото товара, демонстрация результата услуги, промо-фото)
                - "urban_detail" — деталь городской среды (фасад, табличка, дверь, фрагмент здания, фрагмент тротуара, уличный объект крупным планом)
                - "food" — еда или напитки (тарелки, стол, сервировка, кафе)
                - "animal" — животное в фокусе снимка
                - "building" — отдельно стоящее здание целиком
                - "other" — всё, что не подходит под категории выше
                4. Поле "location_type" должно принимать одно из значений:
                - "indoor" — фотография сделана в помещении
                - "outdoor" — фотография сделана на улице / во дворе / на открытом воздухе
                - "mixed" — и помещение, и улица явно присутствуют в кадре
                - "unknown" — невозможно определить
                5. Поле "is_advertising":
                - true — если фотография выглядит как реклама товара или услуги (витрина с выкладкой, фото товара, промо-сцена, демонстрация результата услуги)
                - false — если это бытовой/репортажный кадр.
                6. Поле "situation" — краткое описание ситуации по визуальным признакам. Объясни, что происходит, где, кто чем занят, что пользователь хочет показать. Не описывай чувства/мотивы/биографию.
                7. Поле "user_intent" — интерпретация интенции фотографа по композиции, фокусу, масштабу, ракурсу и типу объекта. Примеры: "показать архитектурную деталь", "задокументировать пространство", "показать товар", "показать еду", "сделать селфи". Не придумывай сложных внутренних мотивов.
                8. Поле "urban_elements" — перечисли элементы городской среды и инфраструктуры (если нет — пустая строка). Примеры: "фасад здания", "стена", "вход", "улица", "тротуар", "дерево", "окно", "граффити".
                9. Поле "urban_practices" — перечисли городские активности (если не видно людей/активностей — пустая строка).
                10. Поле "has_buildings": true, если есть хотя бы одно здание или заметная часть (фасад, стена, вход); иначе false.
    
                11. Используй дополнительный текстовый контекст (описание поста, дату), но не придумывай факты, не подтверждаемые изображением.

                Верни JSON-объект строго следующей структуры:

                {{
                "annotation_text_description": string,
                "annotation_location_type": string,
                "annotation_photo_type": string,
                "annotation_is_advertisement": boolean,
                "annotation_situation_summary": string,
                "annotation_city_objects": string,
                "annotation_city_activities": string,
                "annotation_user_intent": string,
                "annotation_has_building": boolean,
                "annotation_confidence": number (0-1)
                }}

                """
        ).strip()

        content = [
            {"type": "input_text", "text": prompt},
            {
                "type": "input_text",
                "text": (
                    "Дополнительный контекст: "
                    f"описание поста: {photo_row.get('post_text', '') or 'нет описания'}. "
                    "Дата и время: "
                    f"{photo_row.get('date_human', 'unknown')}. "
                    f"POI: {poi_label}."
                ),
            },
        ]

        resized_image_url = build_resized_image_url(photo_row.get("image_url"), target_width=360)
        image_for_model = resized_image_url or photo_row.get("image_url")
        content.append(
            {
                "type": "input_image",
                "image_url": image_for_model,
            }
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
        elif building_focus in {"synagogue", "feor"}:
            verify_result = self._verify_special_building(
                image_for_model,
                building_focus,
                poi_label,
                photo_id,
            )
            if verify_result is not None:
                if building_focus == "synagogue":
                    parsed["annotation_has_synagogue"] = verify_result
                    if verify_result:
                        parsed["annotation_has_other_building"] = bool(
                            parsed.get("annotation_has_other_building")
                        )
                elif building_focus == "feor":
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
        reference = self.reference_map.get(building_focus)
        if not reference:
            return None

        label, payload = reference
        prompt = textwrap.dedent(
            f"""
            Ты сравниваешь здание на фото с эталонным изображением {building_focus}.
            Ответь только JSON-объектом с полями:
            {{
              "matches_reference": boolean,
              "verification_confidence": number (0-1)
            }}
            Установи matches_reference=true только если здание на фото уверенно совпадает со справочным ({label}). При сомнении возвращай false.
            POI: {poi_label}
            """
        ).strip()

        content = [
            {"type": "input_text", "text": prompt},
            {"type": "input_image", "image_url": image_url},
            {
                "type": "input_text",
                "text": f"Справочное изображение ({building_focus}): {label}",
            },
            payload,
        ]

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
        photo_id = str(row["photo_id"])
        cache_path = cache_dir / f"{photo_id}.json"

        if resume:
            cached = None
            if checkpoint.should_skip(photo_id) or cache_path.exists():
                cached = _load_cached_annotation(cache_path)
            if cached is not None:
                annotations[photo_id] = cached
                checkpoint.mark_complete(photo_id)
                continue
            if checkpoint.should_skip(photo_id):
                logging.warning(
                    "Checkpoint referenced %s but cache missing; re-running.", photo_id
                )

        if model_client is None:
            annotation = default_annotation()
        else:
            try:
                annotation = model_client.annotate(row.to_dict())
            except Exception as exc:  # pragma: no cover - network errors
                logging.error("Model failed for photo %s: %s", photo_id, exc)
                annotation = default_annotation()

        annotations[photo_id] = annotation
        checkpoint.mark_complete(photo_id)
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
        annotation = annotations.get(str(record["photo_id"]), default_annotation())
        record.update(annotation)
        merged_records.append(record)

    merged = pd.DataFrame(merged_records)
    missing_cols = [col for col in CSV_COLUMNS if col not in merged.columns]
    for col in missing_cols:
        merged[col] = None
    merged = merged[CSV_COLUMNS]
    return merged


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

        records.append(record)

    enriched = pd.DataFrame(records)
    return enriched


# ---------------------------------------------------------------------------
# Golden set helpers


def create_golden_draft(enriched_csv: Path, output_dir: Path, sample_size: int, seed: int, strategy: str) -> Path:
    df = load_csv(enriched_csv)
    if strategy == "recent" and "date_human" in df.columns:
        df = df.sort_values("date_human", ascending=False)
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
    df = load_csv(args.input_csv)

    if args.shuffle:
        df = df.sample(frac=1.0, random_state=41).reset_index(drop=True)
    if args.limit:
        df = df.head(args.limit)        

    related_links = normalize_related_links(df)

    if args.skip_user_fetch:
        user_info = {}
    else:
        fetcher = VKUserMetadataFetcher(
            token=args.vk_token,
            cache_file=args.cache_dir / "users.json",
        )
        user_info = fetcher.enrich(df["user_id"].unique())

    enriched = restructure_dataframe(df, related_links, user_info)

    model_client: Optional[MultimodalModelClient] = None
    if args.model_provider == "openai":
        references = []
        syn_ref = load_reference_image(args.reference_synagogue)
        if syn_ref:
            references.append(("synagogue", syn_ref[0], syn_ref[1]))
        feor_ref = load_reference_image(args.reference_feor)
        if feor_ref:
            references.append(("feor", feor_ref[0], feor_ref[1]))
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
        for photo_id, payload in annotations.items():
            f.write(
                json.dumps(
                    {"photo_id": photo_id, **payload},
                    ensure_ascii=False,
                )
                + "\n"
            )
    logging.info("Model responses exported to %s", args.model_responses)


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

