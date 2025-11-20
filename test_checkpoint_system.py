#!/usr/bin/env python3
"""
Test script to demonstrate the checkpoint system functionality.
"""

import json
from datetime import datetime
from pathlib import Path
from scripts.collect_vk_photos import (
    create_config_hash, 
    save_checkpoint, 
    load_checkpoint, 
    delete_checkpoint,
    CHECKPOINT_FILE
)


def test_checkpoint_system():
    """Test the checkpoint save/load/delete functionality."""
    
    print("="*70)
    print("Testing Checkpoint System")
    print("="*70)
    
    # Test configuration
    test_pois = [
        {'name': 'Test POI 1', 'lat': 58.0105, 'lon': 56.2502},
        {'name': 'Test POI 2', 'lat': 58.0074, 'lon': 56.2293}
    ]
    start_date = datetime(2024, 1, 1)
    end_date = datetime(2024, 12, 31)
    radius = 300
    output_csv = 'test_photos.csv'
    
    # Test 1: Create config hash
    print("\n1. Testing config hash creation...")
    config_hash = create_config_hash(test_pois, start_date, end_date, radius, output_csv)
    print(f"   Config hash: {config_hash[:16]}...")
    assert len(config_hash) == 64, "Hash should be 64 characters (SHA256)"
    print("   ✓ PASS")
    
    # Test 2: Save checkpoint
    print("\n2. Testing checkpoint save...")
    test_date_timestamp = int(datetime(2024, 6, 15).timestamp())
    save_checkpoint(
        checkpoint_file=CHECKPOINT_FILE,
        config_hash=config_hash,
        pois=test_pois,
        start_date=start_date,
        end_date=end_date,
        radius=radius,
        output_csv=output_csv,
        current_poi_index=1,
        current_date_timestamp=test_date_timestamp,
        photos_collected=150,
        total_photos=150
    )
    assert Path(CHECKPOINT_FILE).exists(), "Checkpoint file should exist"
    print("   ✓ PASS - Checkpoint file created")
    
    # Test 3: Load checkpoint with matching config
    print("\n3. Testing checkpoint load (matching config)...")
    loaded_data = load_checkpoint(CHECKPOINT_FILE, config_hash)
    assert loaded_data is not None, "Should load checkpoint with matching config"
    assert loaded_data['config_hash'] == config_hash, "Config hash should match"
    assert loaded_data['progress']['photos_collected'] == 150, "Should restore photo count"
    assert loaded_data['progress']['current_poi_index'] == 1, "Should restore POI index"
    assert 'current_date_timestamp' in loaded_data['progress'], "Should have date timestamp"
    print(f"   Loaded checkpoint data:")
    print(f"     - Photos collected: {loaded_data['progress']['photos_collected']}")
    print(f"     - Current POI index: {loaded_data['progress']['current_poi_index']}")
    print(f"     - Current date: {loaded_data['progress'].get('current_date_human', 'N/A')}")
    print(f"     - Timestamp: {loaded_data['timestamp']}")
    print("   ✓ PASS")
    
    # Test 4: Load checkpoint with different config
    print("\n4. Testing checkpoint load (mismatched config)...")
    different_pois = [{'name': 'Different POI', 'lat': 59.0, 'lon': 57.0}]
    different_hash = create_config_hash(different_pois, start_date, end_date, radius, output_csv)
    loaded_data = load_checkpoint(CHECKPOINT_FILE, different_hash)
    assert loaded_data is None, "Should return None for mismatched config"
    print("   ✓ PASS - Correctly rejected mismatched config")
    
    # Test 5: Verify checkpoint file content
    print("\n5. Testing checkpoint file structure...")
    with open(CHECKPOINT_FILE, 'r') as f:
        checkpoint_content = json.load(f)
    
    required_fields = ['version', 'timestamp', 'config_hash', 'config', 'progress']
    for field in required_fields:
        assert field in checkpoint_content, f"Checkpoint should have '{field}' field"
    
    print(f"   Checkpoint file structure:")
    print(f"     - Version: {checkpoint_content['version']}")
    print(f"     - Has all required fields: {', '.join(required_fields)}")
    print("   ✓ PASS")
    
    # Test 6: Delete checkpoint
    print("\n6. Testing checkpoint deletion...")
    delete_checkpoint(CHECKPOINT_FILE)
    assert not Path(CHECKPOINT_FILE).exists(), "Checkpoint file should be deleted"
    print("   ✓ PASS - Checkpoint file deleted")
    
    # Test 7: Load non-existent checkpoint
    print("\n7. Testing load of non-existent checkpoint...")
    loaded_data = load_checkpoint(CHECKPOINT_FILE, config_hash)
    assert loaded_data is None, "Should return None when checkpoint doesn't exist"
    print("   ✓ PASS")
    
    print("\n" + "="*70)
    print("All checkpoint system tests passed! ✓")
    print("="*70)


def demonstrate_checkpoint_workflow():
    """Demonstrate how the checkpoint system works in practice."""
    
    print("\n\n" + "="*70)
    print("Checkpoint System Workflow Demo")
    print("="*70)
    
    print("\nScenario: You're collecting photos from 5 POIs")
    print("           Each POI has ~100 photos")
    print("           Checkpoint saves every 100 photos\n")
    
    pois = [f"POI {i+1}" for i in range(5)]
    
    print("Progress timeline:")
    print("  0. 🚀 Start collection")
    print("  1. ✓ Collected 50 photos from POI 1")
    print("  2. ✓ Collected 70 photos from POI 2 (120 total)")
    print("  3. 💾 CHECKPOINT #1 saved (120 photos, starting POI 3)")
    print("  4. ✓ Collected 90 photos from POI 3")
    print("  5. ✓ Collected 60 photos from POI 4 (270 total)")
    print("  6. 💾 CHECKPOINT #2 saved (270 photos, starting POI 5)")
    print("  7. ⚠️  SCRIPT INTERRUPTED! (Ctrl+C or network error)")
    print()
    print("  8. 🔄 Restart script...")
    print("  9. 📂 CHECKPOINT #2 found and loaded")
    print(" 10. ⏩ Resume from POI 5 (270 photos already saved)")
    print(" 11. ✓ Collected 80 photos from POI 5")
    print(" 12. ✅ Collection complete! (350 total photos)")
    print(" 13. 🗑️  Checkpoint file deleted")
    
    print("\n" + "="*70)
    print("Key Benefits:")
    print("  ✓ No data loss on interruption")
    print("  ✓ Resume exactly where you left off")
    print("  ✓ Configuration changes detected automatically")
    print("  ✓ CSV saved incrementally (every 100 photos)")
    print("="*70)


def show_checkpoint_file_example():
    """Show what a checkpoint file looks like."""
    
    print("\n\n" + "="*70)
    print("Example Checkpoint File Content")
    print("="*70)
    
    example_checkpoint = {
        "version": "1.1",
        "timestamp": "2024-11-01T14:30:45.123456",
        "config_hash": "a7f3e8d2c1b4f9e6d5a3c2b1e4f7d6a5...",
        "config": {
            "pois": [
                {"name": "Perm Synagogue", "lat": 58.0105, "lon": 56.2502},
                {"name": "Khabar Restaurant", "lat": 58.0074, "lon": 56.2293},
                {"name": "Jewish Cemetery", "lat": 58.0297, "lon": 56.2345}
            ],
            "start_date": "2024-01-01T00:00:00",
            "end_date": "2024-12-31T23:59:59",
            "radius": 300,
            "output_csv": "vk_photos_perm.csv"
        },
        "progress": {
            "current_poi_index": 2,
            "current_date_timestamp": 1704153600,
            "current_date_human": "2024-06-15",
            "photos_collected": 270,
            "total_photos": 0,
            "completed_pois": 2
        }
    }
    
    print("\n")
    print(json.dumps(example_checkpoint, indent=2))
    print("\n" + "="*70)
    print("This checkpoint shows:")
    print("  - 270 photos collected so far")
    print("  - Current POI: index 2 (Jewish Cemetery)")
    print("  - Current date: 2024-06-15 (will resume from this date)")
    print("  - Config hash ensures configuration hasn't changed")
    print("  - Timestamp shows when checkpoint was created")
    print("="*70)


if __name__ == '__main__':
    try:
        test_checkpoint_system()
        demonstrate_checkpoint_workflow()
        show_checkpoint_file_example()
        
        print("\n\n🎉 All tests completed successfully!")
        print("\nThe checkpoint system is ready to use.")
        print("It will automatically save progress every 100 photos.")
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        # Clean up
        if Path(CHECKPOINT_FILE).exists():
            Path(CHECKPOINT_FILE).unlink()
        exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        # Clean up
        if Path(CHECKPOINT_FILE).exists():
            Path(CHECKPOINT_FILE).unlink()
        import traceback
        traceback.print_exc()
        exit(1)

