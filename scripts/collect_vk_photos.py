#!/usr/bin/env python3
"""
VK Photo Collection Script
Collects photos from VK API within 300m radius of specified POIs and saves to CSV.
"""

import os
import sys
import time
import math
import json
import hashlib
import requests
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

from pois_config import DATE_RANGES, PERM_POIS as POIS, RADIUS_SETTINGS


# Configuration
VK_API_VERSION = '5.131'
POI_RADIUS_METERS = RADIUS_SETTINGS['normal']  # 300 meters around each POI
MAX_PHOTOS_PER_REQUEST = 50
REQUEST_DELAY = 0.35  # seconds between requests to avoid rate limiting
CHECKPOINT_INTERVAL = 30  # Save checkpoint every N photos
CHECKPOINT_FILE = '.vk_collection_checkpoint.json'


def get_vk_token():
    """Safely retrieve VK API token from environment."""
    token = os.environ.get('VK_TOKEN')
    if not token:
        raise ValueError(
            "VK_TOKEN environment variable is not set.\n"
            "Please set it with: export VK_TOKEN='your_token_here'"
        )
    return token


def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance in meters between two points 
    on the earth (specified in decimal degrees).
    """
    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    
    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    # Radius of earth in meters
    r = 6371000
    return c * r


def get_config_hash(pois, start_date, end_date, radius, output_csv):
    """
    Generate a hash of the configuration to detect changes.
    
    Args:
        pois: List of POI dictionaries
        start_date: Start date
        end_date: End date
        radius: Search radius
        output_csv: Output file path
    
    Returns:
        MD5 hash string of configuration
    """
    config_str = json.dumps({
        'pois': sorted([f"{p['name']}:{p['lat']}:{p['lon']}" for p in pois]),
        'start_date': start_date.isoformat(),
        'end_date': end_date.isoformat(),
        'radius': radius,
        'output_csv': output_csv
    }, sort_keys=True)
    return hashlib.md5(config_str.encode()).hexdigest()


def save_checkpoint(checkpoint_file, config_hash, current_poi_idx, collected_photos, 
                   pois, start_date, end_date, radius, output_csv):
    """
    Save checkpoint data to file.
    
    Args:
        checkpoint_file: Path to checkpoint file
        config_hash: Configuration hash
        current_poi_idx: Current POI index being processed
        collected_photos: Total number of photos collected so far
        pois: List of POIs
        start_date: Start date
        end_date: End date
        radius: Search radius
        output_csv: Output CSV file path
    """
    checkpoint_data = {
        'config_hash': config_hash,
        'timestamp': datetime.now().isoformat(),
        'current_poi_idx': current_poi_idx,
        'collected_photos': collected_photos,
        'config': {
            'pois_count': len(pois),
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'radius': radius,
            'output_csv': output_csv
        }
    }
    
    try:
        with open(checkpoint_file, 'w') as f:
            json.dump(checkpoint_data, f, indent=2)
        print(f"💾 Checkpoint saved: {collected_photos} photos collected, POI {current_poi_idx + 1}/{len(pois)}")
    except Exception as e:
        print(f"⚠️  Warning: Failed to save checkpoint: {e}")


def load_checkpoint(checkpoint_file):
    """
    Load checkpoint data from file.
    
    Args:
        checkpoint_file: Path to checkpoint file
    
    Returns:
        Dictionary with checkpoint data, or None if file doesn't exist or is invalid
    """
    if not Path(checkpoint_file).exists():
        return None
    
    try:
        with open(checkpoint_file, 'r') as f:
            checkpoint_data = json.load(f)
        
        # Validate required fields
        required_fields = ['config_hash', 'current_poi_idx', 'collected_photos', 'config']
        if not all(field in checkpoint_data for field in required_fields):
            print("⚠️  Checkpoint file is invalid (missing fields)")
            return None
        
        return checkpoint_data
    except Exception as e:
        print(f"⚠️  Failed to load checkpoint: {e}")
        return None


def checkpoint_matches_config(checkpoint_data, config_hash):
    """
    Check if checkpoint matches current configuration.
    
    Args:
        checkpoint_data: Loaded checkpoint data
        config_hash: Current configuration hash
    
    Returns:
        True if configurations match, False otherwise
    """
    return checkpoint_data['config_hash'] == config_hash


def delete_checkpoint(checkpoint_file):
    """
    Delete checkpoint file after successful completion.
    
    Args:
        checkpoint_file: Path to checkpoint file
    """
    try:
        if Path(checkpoint_file).exists():
            Path(checkpoint_file).unlink()
            print("✓ Checkpoint file cleaned up")
    except Exception as e:
        print(f"⚠️  Warning: Failed to delete checkpoint file: {e}")


def get_photos_for_single_day(token, lat, lon, radius, date_timestamp, end_date_timestamp=None):
    """
    Fetch photos from VK API for a specific location and single day.
    
    Args:
        token: VK API access token
        lat: Latitude of the center point
        lon: Longitude of the center point
        radius: Search radius in meters (max 5000)
        date_timestamp: Unix timestamp for the day to fetch
    
    Returns:
        List of photo items from VK API for that day
    """
    url = 'https://api.vk.com/method/photos.search'
    all_items = []
    
    # VK API limits radius to 5000m, so we'll filter further client-side
    api_radius = min(radius, 5000)
    if end_date_timestamp is None:
        end_date_timestamp = date_timestamp + 86400
    
    params = {
        'access_token': token,
        'v': VK_API_VERSION,
        'sort': 1,  # Sort by date
        'lat': lat,
        'long': lon,
        'radius': api_radius,
        'start_time': date_timestamp,
        'end_time': end_date_timestamp,
        'count': MAX_PHOTOS_PER_REQUEST,
        'offset': 0,
    }
    
    offset = 0
    while True:
        try:
            params['offset'] = offset

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if 'error' in data:
                print(f"VK API Error: {data['error'].get('error_msg', 'Unknown error')}")
                break
            
            if 'response' not in data:
                print(f"Unexpected response format: {data}")
                break
            
            items = data['response'].get('items', [])
            count = data['response'].get('count', 0)
            
            all_items.extend(items)
            
            date_str = datetime.fromtimestamp(date_timestamp).strftime('%Y-%m-%d')
            print(f'  Fetched {len(items)}/{MAX_PHOTOS_PER_REQUEST} photos. '
                f'Total today: {len(all_items)}. Date: {date_str}')
            
            if len(items) == 0:
                break
            
            offset += MAX_PHOTOS_PER_REQUEST
            
            # Rate limiting
            time.sleep(REQUEST_DELAY)
        
        except requests.exceptions.RequestException as e:
            print(f"  Request error: {e}")
            break
        except Exception as e:
            print(f"  Unexpected error: {e}")
            break
    
    return all_items


def filter_photos_by_distance(photos, poi_lat, poi_lon, max_distance_meters):
    """
    Filter photos to only include those within max_distance_meters of POI.
    
    Args:
        photos: List of photo items from VK API
        poi_lat: POI latitude
        poi_lon: POI longitude
        max_distance_meters: Maximum distance in meters
    
    Returns:
        List of filtered photos with distance information
    """
    filtered = []
    
    for photo in photos:
        # Skip photos without location data
        if 'lat' not in photo or 'long' not in photo:
            continue
        
        photo_lat = photo['lat']
        photo_lon = photo['long']
        
        # Calculate distance
        distance = haversine_distance(poi_lat, poi_lon, photo_lat, photo_lon)
        
        # Only include photos within the radius
        if distance <= max_distance_meters:
            photo['distance_meters'] = distance
            photo['poi_lat'] = poi_lat
            photo['poi_lon'] = poi_lon
            filtered.append(photo)
    
    return filtered


def extract_photo_data(photo):
    """
    Extract relevant data from VK photo item.
    
    Args:
        photo: Photo item from VK API
    
    Returns:
        Dictionary with extracted photo data
    """
    # Get the largest image URL
    largest_size = max(photo.get('sizes', []), key=lambda x: x.get('width', 0) * x.get('height', 0))
    image_url = largest_size.get('url', '') if largest_size else ''
    
    # Determine user_id
    user_id = photo.get('user_id')
    if not user_id or user_id == 100:
        user_id = photo.get('owner_id')
    
    return {
        'photo_id': photo.get('id'),
        'album_id': photo.get('album_id'),
        'owner_id': photo.get('owner_id'),
        'user_id': user_id,
        'date': photo.get('date'),
        'date_human': datetime.fromtimestamp(photo.get('date', 0)).strftime('%Y-%m-%d %H:%M:%S'),
        'lat': photo.get('lat'),
        'long': photo.get('long'),
        'poi_lat': photo.get('poi_lat'),
        'poi_lon': photo.get('poi_lon'),
        'distance_meters': photo.get('distance_meters'),
        'image_url': image_url,
        'text': photo.get('text', ''),
        'has_tags': photo.get('has_tags', False),
        'post_id': photo.get('post_id'),
    }


def load_existing_photos(csv_path):
    """
    Safely load existing photos from CSV file.
    
    Args:
        csv_path: Path to CSV file
    
    Returns:
        DataFrame with existing photos, or empty DataFrame if file doesn't exist
    """
    if not Path(csv_path).exists():
        print(f"No existing file found at {csv_path}. Starting fresh.")
        return pd.DataFrame()
    
    try:
        df = pd.read_csv(csv_path)
        print(f"Loaded {len(df)} existing photos from {csv_path}")
        return df
    except Exception as e:
        print(f"Error loading existing file: {e}")
        print("Starting with empty DataFrame.")
        return pd.DataFrame()


def save_photos_to_csv(photos_df, csv_path, append=True):
    """
    Safely save photos to CSV file with deduplication.
    
    Args:
        photos_df: DataFrame with new photos
        csv_path: Path to CSV file
        append: If True, append to existing file; if False, overwrite
    """
    if photos_df.empty:
        print("No photos to save.")
        return
    
    # Load existing photos if appending
    if append:
        existing_df = load_existing_photos(csv_path)
        
        if not existing_df.empty:
            # Combine and deduplicate based on image_url
            combined_df = pd.concat([existing_df, photos_df], ignore_index=True)
            combined_df = combined_df.drop_duplicates(subset=['image_url'], keep='first')
            
            new_count = len(combined_df) - len(existing_df)
            print(f"Added {new_count} new photos (removed duplicates)")
            photos_df = combined_df
        else:
            print(f"Saving {len(photos_df)} new photos")
    
    # Save to CSV
    try:
        photos_df.to_csv(csv_path, index=False, encoding='utf-8-sig')
        print(f"Successfully saved to {csv_path}")
    except Exception as e:
        print(f"Error saving to CSV: {e}")
        # Try saving to backup file
        backup_path = f"{csv_path}.backup_{int(time.time())}"
        try:
            photos_df.to_csv(backup_path, index=False, encoding='utf-8-sig')
            print(f"Saved to backup file: {backup_path}")
        except Exception as e2:
            print(f"Failed to save backup: {e2}")


def create_config_hash(pois, start_date, end_date, radius, output_csv):
    """
    Create a hash of the configuration to detect changes.
    
    Args:
        pois: List of POI dictionaries
        start_date: Start date (datetime)
        end_date: End date (datetime)
        radius: Search radius in meters
        output_csv: Output CSV filename
    
    Returns:
        SHA256 hash of the configuration
    """
    config_str = json.dumps({
        'pois': sorted([{k: v for k, v in poi.items() if k in ['name', 'lat', 'lon']} for poi in pois],
                      key=lambda x: x['name']),
        'start_date': start_date.isoformat(),
        'end_date': end_date.isoformat(),
        'radius': radius,
        'output_csv': output_csv
    }, sort_keys=True)
    
    return hashlib.sha256(config_str.encode()).hexdigest()


def save_checkpoint(checkpoint_file, config_hash, pois, start_date, end_date, 
                   radius, output_csv, current_poi_index, current_date_timestamp,
                   photos_collected, total_photos):
    """
    Save current progress to checkpoint file.
    
    Args:
        checkpoint_file: Path to checkpoint file
        config_hash: Hash of current configuration
        pois: List of POI dictionaries
        start_date: Start date
        end_date: End date
        radius: Search radius
        output_csv: Output CSV filename
        current_poi_index: Index of current POI being processed
        current_date_timestamp: Unix timestamp of current date being processed
        photos_collected: Number of photos collected so far
        total_photos: Total number of photos in memory
    """
    checkpoint_data = {
        'version': '1.1',  # Incremented version for new format
        'timestamp': datetime.now().isoformat(),
        'config_hash': config_hash,
        'config': {
            'pois': pois,
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'radius': radius,
            'output_csv': output_csv
        },
        'progress': {
            'current_poi_index': current_poi_index,
            'current_date_timestamp': current_date_timestamp,
            'current_date_human': datetime.fromtimestamp(current_date_timestamp).strftime('%Y-%m-%d'),
            'photos_collected': photos_collected,
            'total_photos': total_photos,
            'completed_pois': current_poi_index
        }
    }
    
    try:
        with open(checkpoint_file, 'w') as f:
            json.dump(checkpoint_data, f, indent=2)
        date_str = datetime.fromtimestamp(current_date_timestamp).strftime('%Y-%m-%d')
        print(f"  💾 Checkpoint saved ({photos_collected} photos, at date {date_str})")
    except Exception as e:
        print(f"  ⚠️  Warning: Failed to save checkpoint: {e}")


def load_checkpoint(checkpoint_file, config_hash):
    """
    Load checkpoint file and verify configuration matches.
    
    Args:
        checkpoint_file: Path to checkpoint file
        config_hash: Hash of current configuration
    
    Returns:
        Dictionary with checkpoint data if valid, None otherwise
    """
    if not Path(checkpoint_file).exists():
        return None
    
    try:
        with open(checkpoint_file, 'r') as f:
            checkpoint_data = json.load(f)
        
        # Check if configuration matches
        if checkpoint_data.get('config_hash') != config_hash:
            print(f"\n⚠️  Found checkpoint but configuration has changed.")
            print(f"   Checkpoint will be ignored. Starting fresh collection.")
            return None
        
        # Verify checkpoint version (support both 1.0 and 1.1)
        version = checkpoint_data.get('version')
        if version not in ['1.0', '1.1']:
            print(f"\n⚠️  Checkpoint version {version} not supported. Starting fresh collection.")
            return None
        
        # Migrate old checkpoints (v1.0) to new format
        if version == '1.0':
            progress = checkpoint_data.get('progress', {})
            # Old checkpoints didn't track date, so start from beginning of POI
            if 'current_date_timestamp' not in progress:
                progress['current_date_timestamp'] = None
                checkpoint_data['progress'] = progress
        
        return checkpoint_data
        
    except Exception as e:
        print(f"\n⚠️  Error loading checkpoint: {e}")
        print(f"   Starting fresh collection.")
        return None


def delete_checkpoint(checkpoint_file):
    """Delete checkpoint file after successful completion."""
    try:
        if Path(checkpoint_file).exists():
            Path(checkpoint_file).unlink()
            print(f"  🗑️  Checkpoint file removed")
    except Exception as e:
        print(f"  ⚠️  Warning: Failed to delete checkpoint: {e}")


def collect_photos_for_pois(pois, token, start_date, end_date, radius=POI_RADIUS_METERS, output_csv='vk_photos.csv'):
    """
    Main function to collect photos for multiple POIs with checkpoint support.
    
    Args:
        pois: List of dictionaries with 'name', 'lat', 'lon' keys
        token: VK API token
        start_date: Start date (datetime object)
        end_date: End date (datetime object)
        radius: Search radius in meters
        output_csv: Path to output CSV file
    """
    # Generate checkpoint file path (use global constant with CSV filename)
    checkpoint_file = CHECKPOINT_FILE
    
    # Generate configuration hash
    config_hash = create_config_hash(pois, start_date, end_date, radius, output_csv)
    
    # Try to load checkpoint
    checkpoint_data = load_checkpoint(checkpoint_file, config_hash)
    start_poi_idx = 0
    start_date_timestamp = None
    total_collected = 0
    
    if checkpoint_data:
        progress = checkpoint_data.get('progress', {})
        start_poi_idx = progress.get('current_poi_index', 0)
        start_date_timestamp = progress.get('current_date_timestamp')
        total_collected = progress.get('photos_collected', 0)
        checkpoint_time = checkpoint_data.get('timestamp', 'unknown')
        
        print(f"\n{'='*70}")
        print(f"📂 RESUMING FROM CHECKPOINT")
        print(f"{'='*70}")
        print(f"  Checkpoint time: {checkpoint_time}")
        print(f"  Photos collected: {total_collected}")
        print(f"  Resuming from POI: {start_poi_idx + 1}/{len(pois)} ({pois[start_poi_idx]['name']})")
        if start_date_timestamp:
            resume_date = datetime.fromtimestamp(start_date_timestamp).strftime('%Y-%m-%d')
            print(f"  Resuming from date: {resume_date}")
        print(f"{'='*70}\n")
    
    all_photos = []
    
    start_time = int(start_date.timestamp())
    end_time = int(end_date.timestamp())
    
    if start_poi_idx == 0 and not start_date_timestamp:
        print(f"\n{'='*70}")
        print(f"Starting photo collection")
        print(f"Date range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
        print(f"POI radius: {radius} meters")
        print(f"Number of POIs: {len(pois)}")
        print(f"Checkpoint interval: every {CHECKPOINT_INTERVAL} photos")
        print(f"{'='*70}\n")
    
    photos_since_checkpoint = 0
    
    # Iterate through POIs and dates at top level
    for i in range(start_poi_idx, len(pois)):
        poi = pois[i]
        poi_name = poi.get('name', 'Unknown')
        poi_lat = poi['lat']
        poi_lon = poi['lon']
        
        print(f"\n[{i + 1}/{len(pois)}] Processing POI: {poi_name}")
        print(f"Coordinates: ({poi_lat}, {poi_lon})")
        
        # Determine starting date for this POI
        if i == start_poi_idx and start_date_timestamp:
            # Resume from checkpoint date
            current_start_time = start_date_timestamp
            print(f"  Resuming from date: {datetime.fromtimestamp(current_start_time).strftime('%Y-%m-%d')}")
        else:
            # Start from beginning
            current_start_time = start_time
        
        # Iterate through dates day by day
        step = 86400 * 7
        for date_timestamp in range(current_start_time, end_time, step):
            # Fetch photos for this specific day
            raw_photos = get_photos_for_single_day(
                token, poi_lat, poi_lon, 
                radius=radius,
                date_timestamp=date_timestamp,
                end_date_timestamp=date_timestamp + step
            )
            
            # Filter to exact radius
            filtered_photos = filter_photos_by_distance(
                raw_photos, poi_lat, poi_lon, radius
            )
            
            if filtered_photos:
                print(f"  Found {len(filtered_photos)} photos within {radius}m radius")
            
            # Extract data
            for photo in filtered_photos:
                photo_data = extract_photo_data(photo)
                photo_data['poi_name'] = poi_name
                all_photos.append(photo_data)
            
            photos_since_checkpoint += len(filtered_photos)
            total_collected += len(filtered_photos)
            
            # Save checkpoint every CHECKPOINT_INTERVAL photos
            if photos_since_checkpoint >= CHECKPOINT_INTERVAL:
                print("  💾 Saving photos to CSV...")
                # Save current photos to CSV
                if all_photos:
                    photos_df = pd.DataFrame(all_photos)
                    photos_df = photos_df.sort_values('date', ascending=False)
                    save_photos_to_csv(photos_df, output_csv, append=True)
                    
                    # Clear collected photos since they're saved
                    all_photos = []
                
                # Save checkpoint with current date
                save_checkpoint(
                    checkpoint_file, config_hash, pois, start_date, end_date,
                    radius, output_csv, i, date_timestamp + step,  # Next day
                    total_collected, len(all_photos)
                )
                photos_since_checkpoint = 0
    
    # Save any remaining photos
    if all_photos:
        photos_df = pd.DataFrame(all_photos)
        photos_df = photos_df.sort_values('date', ascending=False)
        save_photos_to_csv(photos_df, output_csv, append=True)
    
    # Final summary
    print(f"\n{'='*70}")
    print(f"Collection completed!")
    print(f"Total photos collected in this session: {total_collected}")
    print(f"{'='*70}\n")
    
    # Delete checkpoint file on successful completion
    delete_checkpoint(checkpoint_file)
    
    # Load and return final DataFrame
    if Path(output_csv).exists():
        final_df = pd.read_csv(output_csv)
        return final_df
    else:
        print("\nNo photos collected.")
        return pd.DataFrame()


def main():
    """Main entry point for the script."""
    
    POIS = PERM_POIS
    START_DATE = datetime.strptime(DATE_RANGES['recent']['start'], '%Y-%m-%d')
    END_DATE = datetime.strptime(DATE_RANGES['recent']['end'], '%Y-%m-%d')
    
    OUTPUT_CSV = 'vk_photos_perm.csv'
    
    try:
        # Get VK token
        token = get_vk_token()
        
        # Collect photos
        photos_df = collect_photos_for_pois(
            pois=POIS,
            token=token,
            start_date=START_DATE,
            end_date=END_DATE,
            output_csv=OUTPUT_CSV
        )
        
        if not photos_df.empty:
            print(f"\n✓ Success! Collected {len(photos_df)} photos")
            print(f"  Output saved to: {OUTPUT_CSV}")
            
            # Print summary statistics
            print(f"\nSummary:")
            print(f"  Date range: {photos_df['date_human'].min()} to {photos_df['date_human'].max()}")
            print(f"  Unique users: {photos_df['user_id'].nunique()}")
            print(f"  Average distance from POI: {photos_df['distance_meters'].mean():.1f}m")
            print(f"  Photos by POI:")
            for poi_name, count in photos_df['poi_name'].value_counts().items():
                print(f"    - {poi_name}: {count}")
        
    except ValueError as e:
        print(f"Configuration error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user.")
        print("💾 Progress has been saved to checkpoint file.")
        print("   Run the script again to resume from where you left off.")
        sys.exit(0)
    except Exception as e:
        print(f"Unexpected error: {e}")
        print("💾 Progress saved to checkpoint file. You can resume later.")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

