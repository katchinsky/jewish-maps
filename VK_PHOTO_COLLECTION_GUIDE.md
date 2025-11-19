# VK Photo Collection Script Guide

This script collects photos from VK (VKontakte) API within a 300-meter radius of specified Points of Interest (POIs) and safely saves them to a CSV file.

## Features

- ✅ Collects photos within **300m radius** of each POI
- ✅ Uses accurate **Haversine distance calculation** (great circle distance)
- ✅ **Safe CSV handling** with deduplication
- ✅ **Automatic rate limiting** to respect VK API limits
- ✅ **Append mode** - won't duplicate existing photos
- ✅ **Error handling** with backup file creation
- ✅ Detailed progress reporting

## Prerequisites

1. **Python 3.7+** with required packages:
```bash
pip install -r requirements.txt
```

2. **VK API Token**: You need a valid VK API access token with photos access permission.
   - Get your token from: https://vk.com/apps?act=manage
   - Or use VK's API documentation: https://dev.vk.com/ru/api/access-token/getting-started

## Setup

### 1. Set your VK API token as an environment variable:

**On macOS/Linux:**
```bash
export VK_TOKEN='your_vk_api_token_here'
```

**On Windows:**
```cmd
set VK_TOKEN=your_vk_api_token_here
```

**Permanently (recommended):**

Add to your shell profile (`~/.zshrc`, `~/.bashrc`, etc.):
```bash
export VK_TOKEN='your_vk_api_token_here'
```

### 2. Configure POIs in the script

Edit `collect_vk_photos.py` and modify the `POIS` list in the `main()` function:

```python
POIS = [
    {
        'name': 'Your POI Name',
        'lat': 58.0105,  # Latitude
        'lon': 56.2502   # Longitude
    },
    # Add more POIs...
]
```

### 3. Set date range (optional)

Adjust the date range in the `main()` function:

```python
START_DATE = datetime(2024, 1, 1)
END_DATE = datetime.now()
```

## Usage

### Basic Usage

Run the script:
```bash
python collect_vk_photos.py
```

### Advanced Usage

You can modify the script's configuration constants at the top:

```python
POI_RADIUS_METERS = 300  # Change search radius
MAX_PHOTOS_PER_REQUEST = 50  # Photos per API request
REQUEST_DELAY = 0.35  # Delay between requests (seconds)
```

## Output

The script creates a CSV file (`vk_photos_perm.csv` by default) with the following columns:

| Column | Description |
|--------|-------------|
| `photo_id` | VK photo ID |
| `album_id` | VK album ID |
| `owner_id` | VK owner/group ID |
| `user_id` | VK user ID who posted |
| `date` | Unix timestamp |
| `date_human` | Human-readable date |
| `lat` | Photo latitude |
| `long` | Photo longitude |
| `poi_lat` | POI latitude |
| `poi_lon` | POI longitude |
| `distance_meters` | Distance from POI in meters |
| `image_url` | Full resolution image URL |
| `text` | Photo caption/text |
| `has_tags` | Whether photo has tags |
| `post_id` | Post ID if from a post |
| `poi_name` | Name of the POI |

## How It Works

1. **For each POI:**
   - Fetches photos from VK API using location search
   - VK API returns photos within ~5km (API limitation)
   
2. **Filtering:**
   - Calculates exact distance using Haversine formula
   - Only keeps photos within 300m of POI center
   
3. **Deduplication:**
   - Loads existing CSV (if exists)
   - Removes duplicate photos based on `image_url`
   - Appends only new photos

4. **Safe Saving:**
   - Creates backup if save fails
   - Uses UTF-8 encoding with BOM for Excel compatibility

## Troubleshooting

### "VK_TOKEN is not set" Error
Make sure you've exported the environment variable:
```bash
echo $VK_TOKEN  # Should display your token
```

### Rate Limiting / API Errors
- The script includes automatic rate limiting (0.35s delay)
- If you hit rate limits, increase `REQUEST_DELAY`
- VK API limits: 3 requests/second for most tokens

### No Photos Found
- Check that your POI coordinates are correct
- Try expanding the date range
- Verify that photos exist in that area using VK's map search

### CSV Encoding Issues
- The script uses UTF-8 with BOM (`utf-8-sig`)
- This ensures compatibility with Excel and Google Sheets
- If issues persist, open with `encoding='utf-8-sig'`

## Example Output

```
======================================================================
Starting photo collection
Date range: 2024-01-01 to 2024-11-01
POI radius: 300 meters
Number of POIs: 3
======================================================================

[1/3] Processing POI: Perm Synagogue
Coordinates: (58.0105, 56.2502)
Fetched 50/50 photos. Total: 150/342. Date range: 2024-01-01 - 2024-06-01
Found 342 photos in API search, 28 within 300m radius

[2/3] Processing POI: Jewish Cemetery North
...

======================================================================
Total photos collected: 67
Added 45 new photos (removed duplicates)
Successfully saved to vk_photos_perm.csv
======================================================================

✓ Success! Collected 67 photos
  Output saved to: vk_photos_perm.csv

Summary:
  Date range: 2024-01-01 09:23:11 to 2024-10-28 18:45:32
  Unique users: 34
  Average distance from POI: 187.3m
  Photos by POI:
    - Perm Synagogue: 28
    - Jewish Cemetery North: 23
    - Jewish Cemetery South: 16
```

## Integration with Existing Workflow

This script can be run periodically to collect new photos:

```bash
# Run weekly via cron
0 0 * * 0 /path/to/venv/bin/python /path/to/collect_vk_photos.py
```

The append mode ensures you won't duplicate existing photos in your dataset.

## Notes

- **Privacy**: Only public photos are collected via VK API
- **Distance Accuracy**: Uses Haversine formula for accuracy (±0.5% error)
- **API Limits**: VK API has radius limit of 5000m, so we filter client-side
- **Performance**: ~3 seconds per POI per year of data (approximate)

## Support

For VK API documentation, visit:
- https://dev.vk.com/ru/method/photos.search
- https://dev.vk.com/ru/reference

For issues with this script, check the error messages and traceback for details.

