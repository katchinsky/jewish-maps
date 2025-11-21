# Jewish Maps

Collect, clean, and visualize open data about Jewish community locations in Perm, Russia.
The repository contains reusable scraping scripts, POI metadata, and lightweight notebooks
for exploring the resulting datasets.

## Project Layout

```
jewish-maps/
├── data/                     # Raw HTML/JSON exports from map providers
├── scripts/                  # All executable helpers
│   ├── run_photo_collection.py      # VK photo pipeline entry point
│   ├── collect_vk_photos.py         # Photo collection + checkpoint logic
│   ├── parse_reviews.py             # Normalize Google/Yandex/2GIS reviews
│   ├── create_heatmap.py            # Folium/Seaborn map rendering
│   ├── analyze_photo_distribution.py# Quick stats/plots
│   ├── visualize_vk_photos_perm.py  # Interactive map builder
│   └── enrich_vk_dataset.py         # (optional) downstream cleanup
├── cemetery.ipynb            # Toldot cemetery exploration
├── ml.ipynb                  # Experimental modelling notebook
├── pois_config.py            # Central POI + radius/date presets
├── reviews.csv               # Output of review parsing
├── vk_photos_perm_historical.csv # Canonical photo export (a.k.a. @vk_photos_perm_historical.csv)
├── vk_photos_perm.csv        # Raw daily scrape (legacy, smaller)
├── vk_photos_perm_*.html     # Visualization outputs
├── scripts/__init__.py       # Marks scripts as a package
├── requirements.txt          # Shared dependencies
├── test_checkpoint_system.py # Checkpoint behaviour smoke test
└── test_distance_calculation.py
```

## Setup

```bash
cd /Users/katchinskiy/jewish-maps
python -m venv .venv            # optional (venv/ already included)
source .venv/bin/activate
pip install -r requirements.txt
export VK_TOKEN='your_vk_api_token'  # required for VK scripts
```

`pois_config.py` stores the default POIs, search radii, and date presets.
Update it before running collection scripts if you need different locations.

## Usage

| Goal | Command | Output |
|------|---------|--------|
| Collect VK photos with checkpointing | `python -m scripts.run_photo_collection` | `@vk_photos_perm_historical.csv` |
| Run the raw collector sample | `python -m scripts.collect_vk_photos` | `vk_photos_perm.csv` |
| Annotate/markup photos + cache results | `python -m scripts.enrich_vk_dataset annotate --input-csv @vk_photos_perm_historical.csv --resume --checkpoint-file cache/enrichment/annotate_checkpoint.json` | `vk_photos_perm_enriched.csv` + `*.model_responses.jsonl` |
| Prepare OpenAI batch input | `python -m scripts.enrich_vk_dataset openai-batch prepare --help` | `openai_batch_input.jsonl` + manifest |
| Parse business reviews | `python -m scripts.parse_reviews --help` | `reviews.csv` |
| Build static heatmaps | `python -m scripts.create_heatmap` | `photo_heatmap.html` / PNG |
| Explore distributions | `python -m scripts.analyze_photo_distribution` | `photo_distribution_analysis.png` |

Notebooks (`cemetery.ipynb`, `ml.ipynb`) can be opened with Jupyter Lab/Notebook once data has been generated.

## Data & Outputs

- `data/` keeps the raw HTML/JSON exports from 2GIS, Google, and Yandex.
- `reviews.csv` aggregates normalized review rows (source, business, rating, text, timestamp).
- `vk_photos_perm*.csv` contain photo metadata (VK IDs, coordinates, POI name, Haversine distance, image URL, caption).
- `photo_heatmap.html` and other folium outputs sit alongside the scripts that generate them.

### VK photo enrichment (`scripts/enrich_vk_dataset.py`)

- Default input: `@vk_photos_perm_historical.csv`. Pass a different file with `--input-csv`.
- New annotation columns include:
  - `annotation_city_objects_and_activities` — текстовый список, какие городские объекты и виды активности видны на фото.
- The CLI writes:
  - `vk_photos_perm_enriched.csv` — merged metadata + model annotations.
  - `vk_photos_perm_enriched.model_responses.jsonl` — raw model payloads for audits.
- Long runs are stoppable via checkpointing:
  - `--checkpoint-file cache/enrichment/annotate_checkpoint.json` keeps processed `photo_id`s.
  - `--checkpoint-interval 25` (default) flushes the checkpoint after every N photos.
  - Restart with `--resume` to skip already-labeled photos using both the checkpoint file and cached per-photo JSON responses.
  - Caches live in `cache/enrichment/model_responses/`; delete them to force a clean rerun.

#### OpenAI Batch mode

Use `python -m scripts.enrich_vk_dataset openai-batch ...` to offload large annotation jobs to OpenAI's Batch API (50% cheaper and higher throughput):

1. `openai-batch prepare` — reads the dataset (same flags as `annotate`), writes a `.jsonl` request file, and saves a manifest with the exact `photo_id` mapping.
2. `openai-batch upload` — uploads the `.jsonl` via the Files API (`--openai-api-key` is required for all API-facing subcommands).
3. `openai-batch create` — starts a batch job using the uploaded file; capture the `batch_id`, `output_file_id`, and `error_file_id`.
4. `openai-batch status|list|cancel` — monitor the job while it runs asynchronously (guaranteed within 24h).
5. `openai-batch results --file-id <output_file_id> --output batch_output.jsonl` — download the finished responses (repeat for the error file if present).
6. `openai-batch apply --batch-output batch_output.jsonl --manifest cache/enrichment/openai_batch_manifest.json --output-csv vk_photos_perm_enriched.csv` — merges the batch results back into the dataset, reproducing the same CSV/model response files as the synchronous pipeline.

This keeps the interactive script lightweight while enabling large backfills under separate rate limits.

## Testing

Simple regression checks live in the project root:

```bash
python test_distance_calculation.py    # validates Haversine helper
python test_checkpoint_system.py       # ensures checkpoint files round-trip
```

Run them whenever `scripts/collect_vk_photos.py` changes.

## Notes

- All scripts now live under `scripts/`; run them with `python -m scripts.<name>` so imports resolve consistently.
- Keep sensitive tokens (e.g., `VK_TOKEN`) in your shell environment; the code never reads from files.
- Generated CSV/HTML artifacts are ignored by git—re-run scripts freely without cleanup.
