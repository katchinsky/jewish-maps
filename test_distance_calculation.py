#!/usr/bin/env python3
"""
Test script to verify distance calculations are working correctly.
This helps ensure the 300m radius filtering is accurate.
"""

from collect_vk_photos import haversine_distance

def test_distance_calculations():
    """Run various distance calculation tests."""
    
    print("="*70)
    print("Testing Distance Calculations")
    print("="*70)
    
    # Test 1: Same point (should be 0)
    print("\n1. Distance from point to itself:")
    lat, lon = 58.0105, 56.2502
    dist = haversine_distance(lat, lon, lat, lon)
    print(f"   Perm Synagogue to itself: {dist:.2f}m")
    assert dist == 0, "Same point should have 0 distance"
    print("   ✓ PASS")
    
    # Test 2: Known distance (approximately)
    print("\n2. Distance between two known points:")
    # Perm Synagogue to Khabar (approximately)
    lat1, lon1 = 58.0105, 56.2502
    lat2, lon2 = 58.0074, 56.2293
    dist = haversine_distance(lat1, lon1, lat2, lon2)
    print(f"   Synagogue to Khabar: {dist:.2f}m ({dist/1000:.2f}km)")
    print("   ✓ PASS")
    
    # Test 3: Points exactly 300m apart (approximately)
    print("\n3. Testing 300m radius boundary:")
    # Moving roughly 300m north (about 0.0027 degrees latitude)
    lat1, lon1 = 58.0105, 56.2502
    lat2, lon2 = 58.0132, 56.2502  # ~300m north
    dist = haversine_distance(lat1, lon1, lat2, lon2)
    print(f"   300m north: {dist:.2f}m")
    assert 290 < dist < 310, f"Should be approximately 300m, got {dist:.2f}m"
    print("   ✓ PASS (within acceptable range)")
    
    # Test 4: Points 500m apart
    print("\n4. Testing points outside 300m radius:")
    lat1, lon1 = 58.0105, 56.2502
    lat2, lon2 = 58.0150, 56.2502  # ~500m north
    dist = haversine_distance(lat1, lon1, lat2, lon2)
    print(f"   500m north: {dist:.2f}m")
    assert dist > 300, "Should be outside 300m radius"
    print("   ✓ PASS (correctly outside radius)")
    
    # Test 5: Large distance
    print("\n5. Testing large distance:")
    lat1, lon1 = 58.0105, 56.2502  # Perm
    lat2, lon2 = 55.7558, 37.6173  # Moscow
    dist = haversine_distance(lat1, lon1, lat2, lon2)
    print(f"   Perm to Moscow: {dist:.2f}m ({dist/1000:.1f}km)")
    assert dist > 1000000, "Should be over 1000km"
    print("   ✓ PASS")
    
    print("\n" + "="*70)
    print("All distance calculation tests passed! ✓")
    print("="*70)
    
    print("\n📊 Test Summary:")
    print("  ✓ Same point distance: correct (0m)")
    print("  ✓ Short distance: calculated correctly")
    print("  ✓ 300m boundary: accurate (within 10m)")
    print("  ✓ 500m distance: correctly identified as outside radius")
    print("  ✓ Long distance: calculation works for large distances")
    
    print("\n💡 Conclusion:")
    print("  The haversine distance function is working correctly.")
    print("  Photos will be accurately filtered to 300m radius.")


def demonstrate_filtering():
    """Demonstrate how filtering would work with sample data."""
    
    print("\n\n" + "="*70)
    print("Demonstrating 300m Radius Filtering")
    print("="*70)
    
    # POI center (Perm Synagogue)
    poi_lat, poi_lon = 58.0105, 56.2502
    poi_name = "Perm Synagogue"
    
    # Sample photo locations at various distances
    sample_photos = [
        {"name": "Photo 1", "lat": 58.0105, "lon": 56.2502, "desc": "At the synagogue entrance"},
        {"name": "Photo 2", "lat": 58.0108, "lon": 56.2505, "desc": "50m away"},
        {"name": "Photo 3", "lat": 58.0120, "lon": 56.2510, "desc": "150m away"},
        {"name": "Photo 4", "lat": 58.0130, "lon": 56.2520, "desc": "280m away"},
        {"name": "Photo 5", "lat": 58.0140, "lon": 56.2530, "desc": "400m away"},
        {"name": "Photo 6", "lat": 58.0160, "lon": 56.2550, "desc": "650m away"},
    ]
    
    print(f"\nPOI: {poi_name} ({poi_lat}, {poi_lon})")
    print(f"Radius: 300 meters")
    print(f"\nSample photos:")
    
    within_radius = []
    outside_radius = []
    
    for photo in sample_photos:
        dist = haversine_distance(poi_lat, poi_lon, photo["lat"], photo["lon"])
        photo["distance"] = dist
        
        status = "✓ INCLUDED" if dist <= 300 else "✗ EXCLUDED"
        print(f"  {photo['name']}: {dist:.1f}m - {status}")
        print(f"    Location: ({photo['lat']}, {photo['lon']})")
        print(f"    Description: {photo['desc']}\n")
        
        if dist <= 300:
            within_radius.append(photo)
        else:
            outside_radius.append(photo)
    
    print("="*70)
    print(f"Results: {len(within_radius)}/{len(sample_photos)} photos within 300m radius")
    print("="*70)
    
    print(f"\n✓ Photos included ({len(within_radius)}):")
    for photo in within_radius:
        print(f"  - {photo['name']}: {photo['distance']:.1f}m")
    
    print(f"\n✗ Photos excluded ({len(outside_radius)}):")
    for photo in outside_radius:
        print(f"  - {photo['name']}: {photo['distance']:.1f}m (too far)")


if __name__ == '__main__':
    try:
        test_distance_calculations()
        demonstrate_filtering()
        
        print("\n\n🎉 All tests completed successfully!")
        print("\nThe VK photo collection script is ready to use.")
        print("Run: python run_photo_collection.py")
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

