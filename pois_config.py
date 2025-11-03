"""
Example POI configuration for Perm, Russia
Based on the data files in the project.

You can customize this and import it in collect_vk_photos.py
"""


PERM_POIS = [
    {
        'name': "or avner habad community center", 
        "lat": 58.00763133477656,
        "lon": 56.255145877976155,
        'description': 'FEOR / Jewish Community Center + School'
    },
    {
        "name": "synagogue",
        "lat": 58.00819896273859,
        "lon": 56.23476395501453,
        "description": "KEROOR / Synagogue"
    },
]

# Date ranges for different collection periods
DATE_RANGES = {
    'recent': {
        'start': '2025-01-01',
        'end': '2025-11-01'
    },
    'historical': {
        'start': '2010-01-01',
        'end': '2025-11-01'
    },
    'all_time': {
        'start': '2010-01-01',
        'end': '2025-11-01'
    }
}

# Different radius settings for different use cases
RADIUS_SETTINGS = {
    'tight': 100,      # 100m - immediate vicinity
    'normal': 300,     # 300m - walking distance
    'extended': 500,   # 500m - extended area
    'wide': 1000,      # 1km - neighborhood
}

if __name__ == '__main__':
    print("POI Configuration for Perm Jewish Sites")
    print("=" * 60)
    print(f"\nTotal POIs: {len(PERM_POIS)}")
    print("\nPOI List:")
    for i, poi in enumerate(PERM_POIS, 1):
        print(f"  {i}. {poi['name']}")
        print(f"     Location: ({poi['lat']}, {poi['lon']})")
        print(f"     Description: {poi['description']}\n")

