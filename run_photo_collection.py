#!/usr/bin/env python3
"""
Ready-to-run script for collecting VK photos at Perm Jewish sites.
Customize the settings below and run this script.
"""

import sys
from datetime import datetime
from pathlib import Path

# Import the main collection function
from collect_vk_photos import collect_photos_for_pois, get_vk_token

# Import POI configuration (or define your own below)
from pois_config import PERM_POIS as POIS, RADIUS_SETTINGS, DATE_RANGES
RADIUS = RADIUS_SETTINGS['tight']
START_DATE = datetime.strptime(DATE_RANGES['historical']['start'], '%Y-%m-%d')
END_DATE = datetime.strptime(DATE_RANGES['historical']['end'], '%Y-%m-%d')

# ============================================================================
# CONFIGURATION - Modify these settings as needed
# ============================================================================

# Date range for photo collection
# START_DATE = datetime(2024, 1, 1)      # Start from this date
# END_DATE = datetime.now()               # Collect up to today

# Output file
OUTPUT_CSV = 'vk_photos_perm_historical.csv'

# Optional: Filter POIs by name (set to None to use all POIs)
SELECTED_POI_NAMES = None

# ============================================================================


def main():
    """Main execution function."""
    
    print("\n" + "="*70)
    print("VK Photo Collection for Perm Jewish Sites")
    print("="*70)
    
    # Filter POIs if selected
    pois_to_use = POIS
    if SELECTED_POI_NAMES:
        pois_to_use = [poi for poi in POIS if poi['name'] in SELECTED_POI_NAMES]
        print(f"\nUsing selected POIs: {', '.join(SELECTED_POI_NAMES)}")
    
    # Validate POIs
    if not pois_to_use:
        print("\nError: No POIs configured!")
        print("Please edit this script and add POI coordinates.")
        sys.exit(1)
    
    # Display configuration
    print(f"\nConfiguration:")
    print(f"  POIs: {len(pois_to_use)}")
    print(f"  Date range: {START_DATE.strftime('%Y-%m-%d')} to {END_DATE.strftime('%Y-%m-%d')}")
    print(f"  Output file: {OUTPUT_CSV}")
    print(f"  Search radius: {RADIUS} meters (default)")
    
    print(f"\nPOIs to search:")
    for i, poi in enumerate(pois_to_use, 1):
        print(f"  {i}. {poi['name']} ({poi['lat']}, {poi['lon']})")
    
    # Get VK token
    try:
        token = get_vk_token()
        print(f"\n✓ VK API token found")
    except ValueError as e:
        print(f"\n✗ Error: {e}")
        print("\nPlease set your VK API token:")
        print("  export VK_TOKEN='your_token_here'")
        sys.exit(1)
    
    # Check for existing checkpoint
    checkpoint_file = '.vk_collection_checkpoint.json'
    if Path(checkpoint_file).exists():
        print(f"\n💾 Found existing checkpoint file!")
        print(f"   The script will automatically resume from where it left off.")
    
    # Confirm before starting
    print(f"\n" + "-"*70)
    response = input("Start photo collection? [y/N]: ").strip().lower()
    if response not in ['y', 'yes']:
        print("Cancelled.")
        sys.exit(0)
    
    # Run collection
    try:
        photos_df = collect_photos_for_pois(
            pois=pois_to_use,
            token=token,
            start_date=START_DATE,
            end_date=END_DATE,
            radius=RADIUS,
            output_csv=OUTPUT_CSV
        )
        
        if not photos_df.empty:
            print(f"\n{'='*70}")
            print(f"✓ SUCCESS! Collected {len(photos_df)} photos")
            print(f"{'='*70}")
            print(f"\nOutput saved to: {Path(OUTPUT_CSV).absolute()}")
            
            # Display summary
            print(f"\n📊 Summary Statistics:")
            print(f"  Total photos: {len(photos_df)}")
            print(f"  Unique users: {photos_df['user_id'].nunique()}")
            print(f"  Date range: {photos_df['date_human'].min()} to {photos_df['date_human'].max()}")
            print(f"  Average distance: {photos_df['distance_meters'].mean():.1f}m")
            
            print(f"\n📍 Photos by POI:")
            poi_counts = photos_df['poi_name'].value_counts()
            for poi_name, count in poi_counts.items():
                percentage = (count / len(photos_df)) * 100
                print(f"  • {poi_name}: {count} photos ({percentage:.1f}%)")
            
            print(f"\n💡 Next steps:")
            print(f"  1. Open {OUTPUT_CSV} in Excel/Google Sheets")
            print(f"  2. Analyze the photo data")
            print(f"  3. Download images using the 'image_url' column")
            print(f"  4. Run this script again to collect new photos (append mode)")
            
        else:
            print(f"\n⚠️  No photos found for the specified criteria.")
            print(f"Try:")
            print(f"  - Expanding the date range")
            print(f"  - Checking POI coordinates")
            print(f"  - Verifying that photos exist in these areas on VK")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user.")
        print("💾 Progress has been saved to checkpoint file.")
        print("   Run the script again to resume from where you left off.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("💾 Progress saved to checkpoint file. You can resume later.")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

