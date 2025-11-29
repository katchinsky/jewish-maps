#!/usr/bin/env python3
"""
Download a predefined set of Google Docs interviews, then group them into
2-5 interview bundles with roughly balanced PDF sizes.

Example:
    python scripts/gdoc_interview_bundler.py --output-dir /tmp/interview_bundles

Dependencies:
    pip install requests PyPDF2
"""
from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence

import requests
from PyPDF2 import PdfMerger


DOC_URLS = '''https://docs.google.com/document/d/1sH0LO7Qnxap1GRx5ZeZPdbkvKrt_ZjvLVldbFQ0TES8/edit?tab=t.0
https://docs.google.com/document/d/19ByXYomlypDXPa1DkpR0S5O2koReaKJ0UqJpLaYZaJk/edit?tab=t.0
https://docs.google.com/document/d/1higcuCnqW-k3CidSqqEk84qJ_o8DPAYjMPq6GxyvBXQ/edit?tab=t.0
https://docs.google.com/document/d/1O7PzgkBEv73T7DlBPp9ZskjoWbrQqiwaVaIPZd8FVTM/edit?tab=t.0
https://docs.google.com/document/d/1Xxk2R1fRhGFYQlzRi_NJCVoSu_M8_kTcbdrWd_VYVqY/edit?tab=t.0
https://docs.google.com/document/d/1FtOzb7z0mog1PjVqPTenWiyCRb5zu8Wl6YeXH6FKpp8/edit?usp=share_link
https://docs.google.com/document/d/1ILprBvPIbkAU2jtnLyV7iJ0E_n774CPJcPhN-5MvVdk/edit?tab=t.0
https://docs.google.com/document/d/1rGlx6NnACaxRMoF9g26z0NiKfL854bTLKc4nRhAYCLo/edit?tab=t.0
https://docs.google.com/document/d/1XrL3EyFHec0lKhU6caeexqCaaoygy99ud9DBD8VYhtk/edit?tab=t.0
https://docs.google.com/document/d/1XrL3EyFHec0lKhU6caeexqCaaoygy99ud9DBD8VYhtk/edit?tab=t.0
https://docs.google.com/document/d/1qGTPG2VZdS3udzqV3GbqaHgM2GMG8wfc-oaA3-KW9qE/edit?usp=share_link
https://docs.google.com/document/d/1pbnwN-kfk2pfhDlBfnX9eBwfd88DETs7qAuOHQCx-MA/edit?usp=share_link
https://docs.google.com/document/d/1RPw0UrAnh7mIUcqmFUPGhAxd9Qu5dhvTkuFY-iDJthg/edit?usp=share_link
https://docs.google.com/document/d/19ByXYomlypDXPa1DkpR0S5O2koReaKJ0UqJpLaYZaJk/edit?tab=t.0
https://docs.google.com/document/d/19ByXYomlypDXPa1DkpR0S5O2koReaKJ0UqJpLaYZaJk/edit?tab=t.0
https://docs.google.com/document/d/1S_5fMWfcG1P_xjwwMFmRDlge01dSi4vEMEZmu44byzQ/edit?tab=t.0
https://docs.google.com/document/d/1iUMB_h4P0tPOa0vh300bwHnom-p4w0fzT4INcpnKQtw/edit?tab=t.0
https://docs.google.com/document/d/1lonRMkqgvlT69jmKvW1LN5hRUzhPbPrkmjDVrpm7gRA/edit?tab=t.0
https://docs.google.com/document/d/1lonRMkqgvlT69jmKvW1LN5hRUzhPbPrkmjDVrpm7gRA/edit?tab=t.0
https://docs.google.com/document/d/11NmAlfX_NOF4d3hj4veEplsVQNMqVosPeis5tKzSR0w/edit?tab=t.0
https://docs.google.com/document/d/1egqWX4dDmJG-S7fGAkfVQ9UqnO7F4sw9XM0BjCGKcCk/edit?tab=t.0
https://docs.google.com/document/d/1efBvln_5q-rgc_O6wCABjPwhD0l13fl6gm8W26EXYWs/edit?tab=t.0
https://docs.google.com/document/d/1toSrLQGAWHx5E9LrZYGuVsZUSxm35ASvIYdaJ54_keE/edit?tab=t.0
https://docs.google.com/document/d/1vt4RjWmbIGP-bI9XbFBGDFIV8DMFI5TVfSlBkJVRHfw/edit?usp=share_link'''.splitlines()


DOC_ID_PATTERN = re.compile(r"/document/d/([a-zA-Z0-9_-]+)")


@dataclass
class DownloadedDoc:
    doc_id: str
    url: str
    pdf_path: Path
    size_bytes: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Download Google Docs interviews and merge them into balanced PDF bundles "
            "containing between 2 and 5 interviews each."
        )
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("interview_bundles"),
        help="Directory for the merged PDF bundles (default: ./interview_bundles)",
    )
    parser.add_argument(
        "--scratch-dir",
        type=Path,
        default=Path("interview_downloads"),
        help="Where to store the individual downloaded PDFs (default: ./interview_downloads)",
    )
    parser.add_argument(
        "--urls-file",
        type=Path,
        help="Optional newline-delimited file with extra Google Doc URLs to include.",
    )
    parser.add_argument(
        "--group-count",
        type=int,
        help="Override the automatic group-count calculation.",
    )
    parser.add_argument(
        "--min-per-group",
        type=int,
        default=2,
        help="Minimum number of interviews per bundle (default: 2).",
    )
    parser.add_argument(
        "--max-per-group",
        type=int,
        default=5,
        help="Maximum number of interviews per bundle (default: 5).",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Optional path for a JSON manifest describing the bundles (default: <output-dir>/manifest.json).",
    )
    parser.add_argument(
        "--keep-individual",
        action="store_true",
        help="Keep already-downloaded individual PDFs instead of overwriting them.",
    )
    return parser.parse_args()


def normalize_urls(urls: Iterable[str]) -> List[str]:
    deduped: List[str] = []
    for raw in urls:
        cleaned = raw.strip()
        if not cleaned or cleaned.startswith("#"):
            continue
        if cleaned not in deduped:
            deduped.append(cleaned)
    return deduped


def extract_doc_id(url: str) -> str:
    match = DOC_ID_PATTERN.search(url)
    if not match:
        raise ValueError(f"Could not extract document ID from URL: {url}")
    return match.group(1)


def export_url(doc_id: str) -> str:
    return f"https://docs.google.com/document/d/{doc_id}/export?format=pdf"


def download_doc(session: requests.Session, doc_id: str, destination: Path, overwrite: bool) -> int:
    if destination.exists() and not overwrite:
        return destination.stat().st_size

    destination.parent.mkdir(parents=True, exist_ok=True)
    response = session.get(export_url(doc_id), stream=True)
    if response.status_code == 403:
        raise PermissionError(
            f"Received HTTP 403 for doc {doc_id}. Ensure the document is shared for download."
        )
    response.raise_for_status()

    with destination.open("wb") as f:
        for chunk in response.iter_content(chunk_size=1 << 14):
            if chunk:
                f.write(chunk)

    return destination.stat().st_size


def download_all(
    urls: Sequence[str],
    scratch_dir: Path,
    overwrite_downloads: bool,
) -> List[DownloadedDoc]:
    session = requests.Session()
    session.headers.update(
        {"User-Agent": "interview-bundler/1.0 (+https://github.com/)"}
    )

    downloads: List[DownloadedDoc] = []
    for url in urls:
        doc_id = extract_doc_id(url)
        pdf_path = scratch_dir / f"{doc_id}.pdf"
        size = download_doc(session, doc_id, pdf_path, overwrite_downloads)
        downloads.append(DownloadedDoc(doc_id=doc_id, url=url, pdf_path=pdf_path, size_bytes=size))

    return downloads


def determine_group_count(
    doc_count: int,
    min_per_group: int,
    max_per_group: int,
    override: int | None = None,
) -> int:
    if doc_count == 0:
        raise ValueError("No documents to process.")

    min_groups = math.ceil(doc_count / max_per_group)
    max_groups = max(1, doc_count // min_per_group)
    if min_groups > max_groups:
        raise ValueError(
            f"Cannot satisfy constraints: {doc_count} docs, "
            f"{min_per_group=} {max_per_group=}. Try relaxing them."
        )

    if override is not None:
        if not (min_groups <= override <= max_groups):
            raise ValueError(
                f"Requested group count {override} is outside the feasible range "
                f"[{min_groups}, {max_groups}] for {doc_count} docs."
            )
        return override

    avg_target = (min_per_group + max_per_group) / 2
    suggested = math.ceil(doc_count / avg_target)
    return min(max(suggested, min_groups), max_groups)


def assign_groups(
    docs: Sequence[DownloadedDoc],
    group_count: int,
    min_per_group: int,
    max_per_group: int,
) -> List[dict]:
    docs_sorted = sorted(docs, key=lambda d: d.size_bytes, reverse=True)
    groups = [{"docs": [], "size": 0} for _ in range(group_count)]

    for doc in docs_sorted:
        eligible = [
            (idx, group)
            for idx, group in enumerate(groups)
            if len(group["docs"]) < max_per_group
        ]
        if not eligible:
            raise RuntimeError("Grouping exceeded maximum group size constraint.")
        target_idx, target_group = min(
            eligible, key=lambda item: (item[1]["size"], len(item[1]["docs"]))
        )
        target_group["docs"].append(doc)
        target_group["size"] += doc.size_bytes

    # Fix underfilled groups by borrowing from the largest groups.
    for group in groups:
        while len(group["docs"]) < min_per_group:
            donor_idx, donor_group = max(
                (
                    (idx, grp)
                    for idx, grp in enumerate(groups)
                    if len(grp["docs"]) > min_per_group
                ),
                key=lambda item: (item[1]["size"], len(item[1]["docs"])),
                default=(None, None),
            )
            if donor_group is None:
                raise RuntimeError("Unable to satisfy min-per-group constraint.")
            moved_doc = donor_group["docs"].pop()
            donor_group["size"] -= moved_doc.size_bytes
            group["docs"].append(moved_doc)
            group["size"] += moved_doc.size_bytes

    return groups


def merge_groups(groups: Sequence[dict], output_dir: Path) -> List[dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifests: List[dict] = []

    for idx, group in enumerate(groups, start=1):
        bundle_path = output_dir / f"bundle_{idx:02d}.pdf"
        merger = PdfMerger(strict=False)
        for doc in group["docs"]:
            merger.append(str(doc.pdf_path))
        with bundle_path.open("wb") as f:
            merger.write(f)
        merger.close()

        manifests.append(
            {
                "bundle_index": idx,
                "bundle_path": str(bundle_path),
                "bundle_size_bytes": bundle_path.stat().st_size,
                "documents": [
                    {
                        "doc_id": doc.doc_id,
                        "source_url": doc.url,
                        "size_bytes": doc.size_bytes,
                        "local_pdf_path": str(doc.pdf_path),
                    }
                    for doc in group["docs"]
                ],
            }
        )

    return manifests


def write_manifest(manifest_path: Path, data: dict) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()
    urls = normalize_urls(DOC_URLS)
    if args.urls_file:
        urls += normalize_urls(args.urls_file.read_text(encoding="utf-8").splitlines())
        urls = normalize_urls(urls)

    downloads = download_all(
        urls,
        scratch_dir=args.scratch_dir,
        overwrite_downloads=not args.keep_individual,
    )

    group_count = determine_group_count(
        doc_count=len(downloads),
        min_per_group=args.min_per_group,
        max_per_group=args.max_per_group,
        override=args.group_count,
    )

    groups = assign_groups(
        docs=downloads,
        group_count=group_count,
        min_per_group=args.min_per_group,
        max_per_group=args.max_per_group,
    )

    manifests = merge_groups(groups, args.output_dir)

    manifest_path = args.manifest or args.output_dir / "manifest.json"
    write_manifest(
        manifest_path,
        {
            "total_documents": len(downloads),
            "group_count": group_count,
            "min_per_group": args.min_per_group,
            "max_per_group": args.max_per_group,
            "bundles": manifests,
        },
    )
    print(f"Created {len(manifests)} bundles in {args.output_dir.resolve()}")
    print(f"Manifest written to {manifest_path.resolve()}")


if __name__ == "__main__":
    main()

