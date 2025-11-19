# Getting Started with VK Photo Collection

A quick start guide to begin collecting VK photos near your Points of Interest.

## ✅ What You Have Now

I've converted your notebook into a complete, production-ready photo collection system with:

1. **Core library** (`collect_vk_photos.py`)
   - Accurate 300m radius filtering using Haversine formula
   - Safe CSV operations with deduplication
   - VK API integration with rate limiting

2. **Ready-to-run script** (`run_photo_collection.py`)
   - Interactive interface
   - Pre-configured with Perm POIs
   - Easy customization

3. **Configuration file** (`pois_config_example.py`)
   - All your POI coordinates
   - Easy to modify and extend

4. **Complete documentation**
   - `VK_PHOTO_COLLECTION_GUIDE.md` - Detailed usage guide
   - `README_VK_PHOTOS.md` - Project overview
   - This file - Quick start

5. **Testing suite** (`test_distance_calculation.py`)
   - Verified distance calculations are accurate
   - All tests passing ✓

## 🚀 Quick Start (3 steps)

### Step 1: Get Your VK API Token

Visit https://vk.com/apps?act=manage and create an app to get an access token.

### Step 2: Set Your Token

```bash
export VK_TOKEN='your_vk_api_token_here'
```

To make it permanent, add to `~/.zshrc`:
```bash
echo "export VK_TOKEN='your_token'" >> ~/.zshrc
source ~/.zshrc
```

### Step 3: Run the Collection Script

```bash
cd /Users/katchinskiy/jewish-maps
source venv/bin/activate
python run_photo_collection.py
```

That's it! The script will:
- ✅ Collect photos from all configured POIs
- ✅ Filter to 300m radius for each POI
- ✅ Save to `vk_photos_perm.csv`
- ✅ Show you progress and statistics

## 📝 What Changed from the Notebook

### Before (Notebook)
```python
# Hardcoded coordinates
lat, long = 56.8575, 53.2200

# Manual radius filtering
df['distance'] = df.apply(lambda row: distance(row['lat'], row['long'], lat, long), axis=1)

# No deduplication
df.to_csv('photos.csv', mode='a', header=False)
```

### After (Script)
```python
# Multiple POIs from configuration
POIS = [
    {'name': 'Synagogue', 'lat': 58.0105, 'lon': 56.2502},
    {'name': 'Cemetery', 'lat': 58.0297, 'lon': 56.2345},
    # ... more POIs
]

# Accurate Haversine distance (meters)
distance = haversine_distance(lat1, lon1, lat2, lon2)

# Automatic deduplication
combined_df = combined_df.drop_duplicates(subset=['image_url'], keep='first')
```

### Key Improvements

1. **Accurate Distance Calculation**
   - Uses proper Haversine formula
   - Accounts for Earth's curvature
   - Results in meters (not arbitrary units)

2. **300m Radius Filtering**
   - Precisely 300 meters (tested and verified)
   - Filters client-side after API call
   - VK API limitation workaround

3. **Safe CSV Operations**
   - Automatic deduplication
   - Append mode preserves existing data
   - Backup creation on errors
   - UTF-8 encoding for Excel compatibility

4. **Multiple POIs**
   - Collect from many locations in one run
   - Each photo tagged with POI name
   - Easy to analyze by location

5. **Error Handling**
   - Network errors handled gracefully
   - Rate limiting built-in
   - Clear error messages
   - Backup files on save failures

6. **Checkpoint System** ⭐ NEW!
   - Automatically saves progress every 100 photos
   - Resume from where you left off if interrupted
   - Configuration change detection
   - Zero configuration required

## 📊 Example Output

After running the script, you'll get a CSV file like this:

| photo_id | date_human | poi_name | distance_meters | image_url | text |
|----------|------------|----------|-----------------|-----------|------|
| 12345 | 2024-06-15 14:30:22 | Perm Synagogue | 45.2 | https://... | Beautiful day |
| 67890 | 2024-06-20 09:15:11 | Khabar Restaurant | 128.7 | https://... | Great food |
| 23456 | 2024-07-01 18:22:33 | Jewish Cemetery | 287.3 | https://... | Memorial |

## 🔧 Customization Examples

### Change POIs

Edit `run_photo_collection.py`:
```python
POIS = [
    {'name': 'My Location', 'lat': 58.0000, 'lon': 56.0000}
]
```

### Change Date Range

Edit `run_photo_collection.py`:
```python
START_DATE = datetime(2023, 1, 1)
END_DATE = datetime(2024, 6, 30)
```

### Change Radius

Edit `collect_vk_photos.py`:
```python
POI_RADIUS_METERS = 500  # 500 meters instead of 300
```

### Select Specific POIs

Edit `run_photo_collection.py`:
```python
SELECTED_POI_NAMES = ['Perm Synagogue', 'Khabar Restaurant']
```

## 🔍 Testing

Verify everything works:

```bash
python test_distance_calculation.py
```

This will:
- ✅ Test distance calculations
- ✅ Verify 300m radius filtering
- ✅ Show example filtering results

## 📈 Integration with Your Workflow

You can use this alongside your existing `cemetery.ipynb`:

```python
# In your notebook
import pandas as pd

# Load cemetery data
cemetery_df = pd.read_csv('perm_cemetery_records.csv')

# Load VK photos
photos_df = pd.read_csv('vk_photos_perm.csv')

# Combine for analysis
print(f"Cemetery records: {len(cemetery_df)}")
print(f"VK photos: {len(photos_df)}")
```

## 🔄 Running Periodically

Collect new photos weekly:

```bash
# Add to crontab
0 0 * * 0 cd /Users/katchinskiy/jewish-maps && venv/bin/python run_photo_collection.py
```

The script's append mode ensures no duplicates.

## ⚠️ Common Issues

### "VK_TOKEN is not set"
```bash
# Check if set
echo $VK_TOKEN

# If empty, set it
export VK_TOKEN='your_token'
```

### "No module named 'requests'"
```bash
# Activate venv and install
source venv/bin/activate
pip install -r requirements.txt
```

### No photos found
- Verify POI coordinates are correct
- Check date range is valid
- Try a specific, known location first

## 📚 Next Steps

1. **Run your first collection**
   ```bash
   python run_photo_collection.py
   ```

2. **Analyze the results**
   - Open `vk_photos_perm.csv` in Excel or Google Sheets
   - Check distance distribution
   - Verify photos are within 300m

3. **Customize for your needs**
   - Add more POIs
   - Adjust date ranges
   - Modify radius if needed

4. **Integrate with your analysis**
   - Load data in Jupyter notebooks
   - Create visualizations
   - Combine with other datasets

## 🔄 Interruption & Resume

**New!** The script automatically saves progress every 100 photos.

### If Interrupted

Press Ctrl+C or if the script crashes:
```
⚠️  Interrupted by user.
💾 Progress has been saved to checkpoint file.
   Run the script again to resume from where you left off.
```

### Resume Collection

Simply run the script again:
```bash
python run_photo_collection.py
```

The script automatically detects and resumes:
```
📂 RESUMING FROM CHECKPOINT
  Checkpoint time: 2024-11-01T14:30:45
  Photos collected: 250
  Resuming from POI: 3/5 (Jewish Cemetery)
```

### Configuration Changes

If you change POIs, date range, or radius:
```
⚠️  Found checkpoint but configuration has changed.
   Checkpoint will be ignored. Starting fresh collection.
```

This prevents data inconsistency.

**Learn more:** See [CHECKPOINT_SYSTEM.md](CHECKPOINT_SYSTEM.md) for details.

## 💡 Tips

- **Start small**: Test with one POI first
- **Check coordinates**: Use Google Maps to verify lat/lon
- **Monitor API usage**: VK has rate limits
- **Regular collections**: Run weekly/monthly for fresh data
- **Backup data**: Keep copies of your CSV files
- **Long collections**: Let it run overnight - checkpoints have you covered!

## 🎯 Project Structure

```
jewish-maps/
├── collect_vk_photos.py            # Core library
├── run_photo_collection.py         # Main script to run
├── pois_config.py                  # POI configuration
├── test_distance_calculation.py    # Distance testing
├── test_checkpoint_system.py       # Checkpoint testing ⭐ NEW
├── VK_PHOTO_COLLECTION_GUIDE.md    # Detailed guide
├── README_VK_PHOTOS.md             # Overview
├── GETTING_STARTED.md              # This file
├── CHECKPOINT_SYSTEM.md            # Checkpoint docs ⭐ NEW
├── requirements.txt                # Dependencies (updated)
├── vk_photos_perm.csv             # Output (created when you run)
└── .vk_collection_checkpoint.json  # Checkpoint (auto-created/deleted)
```

## ✅ Verification Checklist

Before your first run:

- [ ] VK_TOKEN environment variable is set
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] POI coordinates verified
- [ ] Date range configured
- [ ] Test script passes (`python test_distance_calculation.py`)

## 🆘 Need Help?

1. Check error messages - they're designed to be helpful
2. Read `VK_PHOTO_COLLECTION_GUIDE.md` for details
3. Run test script to verify setup
4. Check VK API status and limits

---

**Ready to start?**

```bash
python run_photo_collection.py
```

Good luck with your photo collection! 🎉

