# VK Photo Collection Scripts

This directory contains scripts for collecting VK (VKontakte) photos within a 300-meter radius of Points of Interest (POIs) in Perm, Russia.

## 🎯 Quick Start

1. **Set your VK API token:**
   ```bash
   export VK_TOKEN='your_vk_api_token_here'
   ```

2. **Run the collection script:**
   ```bash
   python run_photo_collection.py
   ```

3. **Check the output:**
   - Photos will be saved to `vk_photos_perm.csv`
   - The script will show you statistics and summary

## 📁 Files

### Main Scripts

- **`collect_vk_photos.py`** - Core library with all collection functions
  - Handles VK API requests
  - Filters photos by distance (300m radius)
  - Manages CSV operations with deduplication
  - Can be imported and used in other scripts

- **`run_photo_collection.py`** - Ready-to-run executable script
  - Simple configuration at the top of the file
  - Interactive confirmation before collection
  - Uses POIs from `pois_config_example.py`
  - Displays detailed progress and results

- **`pois_config_example.py`** - POI configuration file
  - Contains coordinates for Perm Jewish sites
  - Easy to customize for different locations
  - Can be imported into other scripts

### Documentation

- **`VK_PHOTO_COLLECTION_GUIDE.md`** - Complete usage guide
  - Detailed setup instructions
  - Configuration options
  - Troubleshooting tips
  - API documentation references

## 🚀 Usage Examples

### Basic Usage (Default Settings)

```bash
python run_photo_collection.py
```

This will:
- Collect photos from all configured POIs
- Search from January 1, 2024 to today
- Save to `vk_photos_perm.csv`
- Use 300m radius for each POI

### Custom Date Range

Edit `run_photo_collection.py`:
```python
START_DATE = datetime(2023, 6, 1)
END_DATE = datetime(2024, 6, 30)
```

### Select Specific POIs

Edit `run_photo_collection.py`:
```python
SELECTED_POI_NAMES = ['Perm Synagogue', 'Khabar Restaurant']
```

### Using as a Library

```python
from collect_vk_photos import collect_photos_for_pois, get_vk_token
from datetime import datetime

token = get_vk_token()
pois = [
    {'name': 'My POI', 'lat': 58.0105, 'lon': 56.2502}
]

photos_df = collect_photos_for_pois(
    pois=pois,
    token=token,
    start_date=datetime(2024, 1, 1),
    end_date=datetime.now(),
    output_csv='my_photos.csv'
)
```

## 📊 Output Format

The CSV file contains these columns:

| Column | Description |
|--------|-------------|
| `photo_id` | VK photo ID |
| `owner_id` | VK owner ID |
| `user_id` | VK user who posted |
| `date` | Unix timestamp |
| `date_human` | Human-readable date |
| `lat`, `long` | Photo coordinates |
| `poi_lat`, `poi_lon` | POI coordinates |
| `distance_meters` | Distance from POI (meters) |
| `image_url` | Full resolution image URL |
| `text` | Photo caption |
| `poi_name` | Name of the associated POI |

## ✨ Features

- ✅ **Accurate distance calculation** using Haversine formula
- ✅ **300m radius filtering** - only photos within 300 meters
- ✅ **Automatic deduplication** - won't add duplicate photos
- ✅ **Safe append mode** - adds new photos without overwriting
- ✅ **Rate limiting** - respects VK API limits
- ✅ **Error handling** - creates backups if save fails
- ✅ **Progress tracking** - shows detailed progress
- ✅ **UTF-8 encoding** - Excel/Google Sheets compatible

## 🛠️ Customization

### Change Search Radius

Edit `collect_vk_photos.py`:
```python
POI_RADIUS_METERS = 500  # Change to 500 meters
```

### Add New POIs

Edit `pois_config_example.py`:
```python
PERM_POIS = [
    {
        'name': 'My New Location',
        'lat': 58.0000,
        'lon': 56.0000,
        'description': 'Description of the place'
    },
    # ... more POIs
]
```

### Change Output Filename

Edit `run_photo_collection.py`:
```python
OUTPUT_CSV = 'my_custom_photos.csv'
```

## 🔧 Troubleshooting

### "VK_TOKEN is not set"
```bash
export VK_TOKEN='your_token_here'
# Or add to ~/.zshrc for permanent setting
```

### No Photos Found
- Verify POI coordinates are correct
- Expand date range
- Check if photos exist in VK for that area
- Try increasing the radius temporarily

### API Rate Limits
Edit `collect_vk_photos.py`:
```python
REQUEST_DELAY = 1.0  # Increase delay to 1 second
```

## 📝 Integration with Existing Workflow

The script is designed to work alongside your existing `cemetery.ipynb` notebook:

1. **Collect cemetery photos** using the notebook (VK scraping for cemetery locations)
2. **Collect POI photos** using this script (VK photos near Jewish sites)
3. **Combine data** for comprehensive analysis

### Running Periodically

Add to crontab for weekly collection:
```bash
0 0 * * 0 cd /Users/katchinskiy/jewish-maps && /path/to/venv/bin/python run_photo_collection.py
```

## 🔒 Privacy & Ethics

- Only collects **public photos** available through VK API
- Respects **VK's rate limits** and terms of service
- No personal data is stored beyond what's in public photos
- Photos are collected for **research/documentation purposes**

## 📚 References

- [VK API Documentation](https://dev.vk.com/ru/method/photos.search)
- [Getting VK Access Token](https://dev.vk.com/ru/api/access-token/getting-started)
- [VK API Rate Limits](https://dev.vk.com/ru/api/api-requests)

## 🆘 Support

For detailed help, see `VK_PHOTO_COLLECTION_GUIDE.md`.

For issues:
1. Check error messages in console output
2. Verify VK_TOKEN is set correctly
3. Ensure internet connection is stable
4. Check VK API status

## 📄 License

This script is part of the jewish-maps project.

---

**Note**: Make sure you have a valid VK API token with appropriate permissions before running these scripts.

