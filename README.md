# Jewish Maps - Perm, Russia

A data collection and analysis project for Jewish historical sites and community locations in Perm, Russia.

## 📋 Overview

This project collects and analyzes data from multiple sources:

1. **Cemetery Records** - Historical burial records from Toldot.com
2. **VK Photos** - Geotagged photos from VKontakte within 300m of Points of Interest
3. **Reviews Data** - Reviews from Google, Yandex, and 2GIS for Jewish community locations

## 🗂️ Project Structure

```
jewish-maps/
├── cemetery.ipynb                 # Cemetery data scraping notebook
├── ml.ipynb                       # Machine learning analysis
├── parse_reviews.py               # Review parsing script
├── create_heatmap.py              # Heatmap generation
│
├── collect_vk_photos.py           # ⭐ VK photo collection library
├── run_photo_collection.py        # ⭐ Ready-to-run photo collector
├── pois_config_example.py         # ⭐ POI configuration
├── test_distance_calculation.py   # ⭐ Testing suite
│
├── reviews.csv                    # Collected reviews data
├── vk_photos_perm.csv            # Collected VK photos (generated)
│
├── data/                          # Source data files
│   ├── yandex-*.json             # Yandex Maps data
│   ├── google-*.html/txt         # Google Maps data
│   └── 2gis-*.html               # 2GIS data
│
└── requirements.txt               # Python dependencies
```

## 🆕 New: VK Photo Collection Scripts

**Just added!** A complete photo collection system that safely collects VK photos within 300m of your POIs.

### Quick Start

1. **Set your VK API token:**
   ```bash
   export VK_TOKEN='your_vk_api_token'
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the collector:**
   ```bash
   python run_photo_collection.py
   ```

### Features

- ✅ **300m radius filtering** - Accurate Haversine distance calculation
- ✅ **Safe CSV operations** - Automatic deduplication and append mode
- ✅ **Multiple POIs** - Collect from many locations in one run
- ✅ **Rate limiting** - Respects VK API limits
- ✅ **Error handling** - Backup creation on failures
- ✅ **Checkpoint system** - Resume interrupted collections automatically

### Documentation

- **[GETTING_STARTED.md](GETTING_STARTED.md)** - Quick start guide (start here!)
- **[VK_PHOTO_COLLECTION_GUIDE.md](VK_PHOTO_COLLECTION_GUIDE.md)** - Detailed usage guide
- **[README_VK_PHOTOS.md](README_VK_PHOTOS.md)** - Photo collection overview
- **[CHECKPOINT_SYSTEM.md](CHECKPOINT_SYSTEM.md)** - Checkpoint and resume functionality

### Testing

Verify the system works:
```bash
python test_distance_calculation.py
```

## 📍 Points of Interest (POIs)

The project tracks several Jewish community locations in Perm:

1. **Perm Synagogue** - Main synagogue
2. **Khabar Restaurant** - Jewish/Kosher restaurant  
3. **Jewish Cemeteries** - North and South locations
4. **Community Centers** - Various venues
5. **Historical Sites** - Cemetery markers from 1700s-2020s

See `pois_config_example.py` for complete list with coordinates.

## 📊 Data Sources

### 1. Cemetery Records (Toldot.com)

- Historical burial records
- Names, dates (birth/death), locations
- Cemetery photos (North and South)
- 2,696 records collected

**Access via:** `cemetery.ipynb`

### 2. VK Photos (VKontakte API)

- Geotagged photos within 300m of POIs
- User-generated content
- Photo metadata (date, location, caption)
- Deduplication and safe storage

**Access via:** `run_photo_collection.py`

### 3. Business Reviews

Multiple sources for Jewish community locations:
- **Google Maps** - Reviews and ratings
- **Yandex Maps** - Russian reviews
- **2GIS** - Local business data

**Locations tracked:**
- Synagogues
- Restaurants (Khabar, Poke, Ryumochnaya)
- Museums (VR Museum)
- Businesses (CDEK, Twins, ProBeauty)

**Access via:** `parse_reviews.py`, `reviews.csv`

## 🚀 Getting Started

### Prerequisites

- Python 3.7+
- Virtual environment (included: `venv/`)
- VK API token (for photo collection)

### Installation

1. **Clone the repository** (or cd into it)
   ```bash
   cd /Users/katchinskiy/jewish-maps
   ```

2. **Activate virtual environment**
   ```bash
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up VK API token** (optional, only for photo collection)
   ```bash
   export VK_TOKEN='your_vk_api_token'
   ```

### Usage

#### Collect VK Photos

```bash
python run_photo_collection.py
```

See [GETTING_STARTED.md](GETTING_STARTED.md) for detailed instructions.

#### Analyze Cemetery Data

```bash
jupyter notebook cemetery.ipynb
```

#### Parse Reviews

```bash
python parse_reviews.py
```

#### Generate Heatmaps

```bash
python create_heatmap.py
```

## 📈 Analysis Notebooks

### cemetery.ipynb

- Scrapes cemetery records from Toldot.com
- Analyzes birth/death year distributions
- Visualizes age distributions by year
- Identifies common surnames and names
- Cemetery location analysis (North vs South)

**Key Findings:**
- Birth years: 1700s - 1990s
- Death years: 1800s - 2024
- Common surnames: Goldberg, Levin, Kogan, etc.
- Age distribution analysis by birth cohort

### ml.ipynb

Machine learning analysis on collected data.

## 🗺️ Visualizations

- **Heatmaps** - Geographic distribution of photos
- **Cemetery plots** - Birth/death year distributions
- **Review analysis** - Sentiment and ratings
- **Interactive maps** - Folium-based POI maps

## 📦 Dependencies

```
beautifulsoup4>=4.12.0  # HTML parsing
lxml>=4.9.0             # XML/HTML processing
requests>=2.31.0        # HTTP requests
pandas>=2.0.0           # Data analysis
```

Plus Jupyter ecosystem for notebooks.

## 🔧 Configuration

### POIs

Edit `pois_config_example.py` to customize locations:

```python
PERM_POIS = [
    {
        'name': 'Your Location',
        'lat': 58.0105,
        'lon': 56.2502,
        'description': 'Description'
    },
    # Add more...
]
```

### Date Ranges

In `run_photo_collection.py`:
```python
START_DATE = datetime(2024, 1, 1)
END_DATE = datetime.now()
```

### Search Radius

In `collect_vk_photos.py`:
```python
POI_RADIUS_METERS = 300  # Change as needed
```

## 📝 Data Format

### VK Photos CSV

| Column | Description |
|--------|-------------|
| photo_id | VK photo ID |
| date_human | Human-readable timestamp |
| poi_name | Associated POI |
| distance_meters | Distance from POI |
| lat, long | Photo coordinates |
| image_url | Full resolution URL |
| text | Photo caption |

### Reviews CSV

| Column | Description |
|--------|-------------|
| source | Google/Yandex/2GIS |
| business | Business name |
| rating | Star rating |
| text | Review text |
| date | Review date |

## 🧪 Testing

Run tests to verify functionality:

```bash
# Test distance calculations
python test_distance_calculation.py
```

Expected output:
```
All distance calculation tests passed! ✓
The haversine distance function is working correctly.
Photos will be accurately filtered to 300m radius.
```

## 🔒 Privacy & Ethics

- Only public data is collected
- VK API rate limits are respected
- No personal data stored beyond public profiles
- Data collection for research/documentation purposes

## 📚 Resources

- [VK API Documentation](https://dev.vk.com/ru/method/photos.search)
- [Toldot Cemetery Database](https://toldot.com/life/cemetery/)
- [Haversine Distance Formula](https://en.wikipedia.org/wiki/Haversine_formula)

## 🆘 Troubleshooting

### VK Photo Collection Issues

See [VK_PHOTO_COLLECTION_GUIDE.md](VK_PHOTO_COLLECTION_GUIDE.md) for detailed troubleshooting.

### Common Issues

**"VK_TOKEN is not set"**
```bash
export VK_TOKEN='your_token_here'
```

**"No module named 'requests'"**
```bash
pip install -r requirements.txt
```

**No photos found**
- Check POI coordinates
- Verify date range
- Confirm photos exist in area

## 📊 Project Status

- ✅ Cemetery data collection - Complete (2,696 records)
- ✅ VK photo collection - Implemented and tested
- ✅ Review parsing - Complete
- ✅ Basic analysis - In progress
- 🔄 Machine learning - In development
- 🔄 Heatmap generation - In progress

## 📄 License

[Specify your license here]

## 👤 Author

Project by katchinskiy

## 🙏 Acknowledgments

- Toldot.com for cemetery records
- VK API for photo access
- OpenStreetMap for mapping
- Perm Jewish community

---

**Latest Update:** Added VK photo collection system with 300m radius filtering, safe CSV operations, and comprehensive testing (November 1, 2025)

For detailed instructions on VK photo collection, start with [GETTING_STARTED.md](GETTING_STARTED.md).

