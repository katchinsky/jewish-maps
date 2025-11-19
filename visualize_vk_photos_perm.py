import pandas as pd
import folium
from folium.plugins import HeatMap, MarkerCluster
import webbrowser
import os
import math
from datetime import datetime
import json

POI = {
    "or avner habad community center": {
        "lat": 58.00763133477656,
        "long": 56.255145877976155
    },
    "synagogue": {
        "lat": 58.00819896273859,
        "long": 56.23476395501453
    },
    "building site": {
        "lat": 57.99712113911606,
        "long": 56.191195922468836
    },
}

def get_distance(lat1, long1, lat2, long2):
    return math.sqrt((lat1 - lat2) ** 2 + (long1 - long2) ** 2)

def get_distance_to_poi(lat, long, poi):
    return get_distance(lat, long, POI[poi]["lat"], POI[poi]["long"])

def get_min_distance_to_poi(lat, long):
    distance = float('inf')
    for poi in POI:
        distance = min(distance, get_distance_to_poi(lat, long, poi))
    return distance


def create_heatmap_vk(csv_file, sample_size=2000, distance_threshold_meters=1000):
    """
    Create a heatmap visualization for VK photos data
    
    Args:
        csv_file: Path to the CSV file with VK photos
        sample_size: Number of photos to sample for detailed markers
        distance_threshold_meters: Maximum distance from POI in meters to include photos
    """
    # Read the CSV file
    df = pd.read_csv(csv_file)
    
    # Drop rows without coordinates
    df = df.dropna(subset=['lat', 'long'])
    
    # Filter by distance threshold
    df = df[df['distance_meters'] < distance_threshold_meters]
    
    # Add time-based columns for filtering
    df['datetime'] = pd.to_datetime(df['date'], unit='s')
    df['year'] = df['datetime'].dt.year
    
    print(f"Total photos after filtering: {len(df)}")
    print(f"Distance threshold: {distance_threshold_meters} meters")
    print("\nPhotos by POI:")
    print(df['poi_name'].value_counts())
    
    # Get sorted list of all years
    all_periods = sorted(df['year'].unique())
    
    print(f"\nTime periods: {len(all_periods)}")
    print(f"Range: {all_periods[0]} to {all_periods[-1]}")
    
    # Create the base map centered on the data
    map_center = [df['lat'].mean(), df['long'].mean()]
    my_map = folium.Map(location=map_center, zoom_start=15, tiles=None)
    my_map.add_child(folium.TileLayer('openstreetmap'))
    my_map.add_child(folium.TileLayer('cartodbpositron'))

    # Create feature groups for each time period
    time_feature_groups = {}
    layer_ids = {}  # Store layer IDs for JavaScript access
    for i, period in enumerate(all_periods):
        fg = folium.FeatureGroup(name=f"{period}", show=(period == all_periods[-1]))
        fg.add_to(my_map)
        time_feature_groups[period] = fg
        layer_ids[str(period)] = fg.get_name()  # Store the layer ID
    
    # Add a feature group for POIs themselves
    poi_group = folium.FeatureGroup(name="Points of Interest", show=True).add_to(my_map)
    
    # POI colors
    poi_colors = {
        "or avner habad community center": "blue",
        "synagogue": "purple",
        "building site": "orange"
    }
    
    # Create marker clusters and heatmaps for each year
    marker_clusters = {}
    for period in all_periods:
        period_df = df[df['year'] == period]
        
        # Create marker cluster for this period
        marker_clusters[period] = MarkerCluster().add_to(time_feature_groups[period])
        
        # Add heatmap layer for this period
        heat_data = [[row['lat'], row['long']] for _, row in period_df.iterrows()]
        if heat_data:  # Only add if there's data
            HeatMap(
                heat_data, 
                min_opacity=0.5, 
                max_opacity=0.8, 
                radius=15, 
                gradient={0: 'transparent', 0.2: 'blue', 1: 'red'}
            ).add_to(time_feature_groups[period])

    # Group photos by user_id and year, then aggregate
    user_groups = df.groupby(['owner_id', 'year']).agg({
        'lat': 'median',
        'long': 'median',
        'photo_id': ['count', lambda x: list(x)[:5]],  # Count and list of photo IDs
        'text': lambda x: ' | '.join([str(t) for t in x if pd.notna(t) and t != ''])[:200],  # Combine texts
        'date': 'min',  # First photo date
        'date_human': 'first',
        'distance_meters': 'min',  # Closest distance
        'poi_name': lambda x: x.mode()[0] if len(x.mode()) > 0 else x.iloc[0],  # Most common POI
        'image_url': lambda x:  [url for url in x if pd.notna(url)][:5]  # First 5 images
    }).reset_index()
    
    # Flatten column names and rename
    user_groups.columns = ['owner_id', 'year', 'lat', 'long', 'photo_count', 'photo_ids', 'text', 'date', 'date_human', 'distance_meters', 'poi_name', 'image_url']
    
    print(f"\nTotal unique user-period combinations: {len(user_groups)}")
    print(f"Unique users across all periods: {user_groups['owner_id'].nunique()}")

    # Add one marker per user per time period
    for _, user_row in user_groups.iterrows():
        # Handle missing text
        text = user_row['text'] if user_row['text'] != '' else 'No description'
        
        # Format date
        date_str = user_row['date_human'] if pd.notna(user_row['date_human']) else datetime.fromtimestamp(user_row['date']).strftime('%Y-%m-%d %H:%M:%S')
        
        # Create image gallery HTML with links
        images_html = ""
        photo_links_html = ""
        
        if len(user_row['image_url']) > 0 and len(user_row['photo_ids']) > 0:
            # Main image with link
            images_html = f"<a href='https://vk.com/photo{user_row['owner_id']}_{user_row['photo_ids'][0]}' target='_blank'>"
            images_html += f"<img src='{user_row['image_url'][0]}' style='width: 100%; height: auto; cursor: pointer;'></a>"
            
            # Thumbnails with links
            if len(user_row['image_url']) > 1:
                images_html += "<div style='display: flex; flex-wrap: wrap; gap: 5px; margin-top: 5px;'>"
                for i, img in enumerate(user_row['image_url'][1:], 1):
                    if i < len(user_row['photo_ids']):
                        images_html += f"<a href='https://vk.com/photo{user_row['owner_id']}_{user_row['photo_ids'][i]}' target='_blank'>"
                        images_html += f"<img src='{img}' style='width: 30%; height: auto; cursor: pointer;'></a>"
                images_html += "</div>"
            
            # Create list of photo links
            photo_links_html = "<p><strong>View photos:</strong> "
            photo_links = []
            for i, photo_id in enumerate(user_row['photo_ids'], 1):
                photo_links.append(f"<a href='https://vk.com/photo{user_row['owner_id']}_{photo_id}' target='_blank'>{i}</a>")
            photo_links_html += " | ".join(photo_links) + "</p>"
        
        popup_html = f"""
        <div style="width:350px">
            {images_html}
            <p><strong>User ID: {user_row['owner_id']}</strong></p>
            <p><strong>Photos in {int(user_row['year'])}: {user_row['photo_count']}</strong></p>
            {photo_links_html}
            <p>{text}</p>
            <p>Earliest photo: {date_str}</p>
            <p>Closest distance: {user_row['distance_meters']:.1f}m from {user_row['poi_name']}</p>
            <p><a href="https://vk.com/id{abs(user_row['owner_id'])}" target="_blank">View profile on VK</a></p>
        </div>
        """
        
        color = poi_colors.get(user_row['poi_name'], 'gray')
        
        # Calculate marker radius based on photo count (min 5, max 25)
        radius = min(5 + (user_row['photo_count'] * 0.5), 25)
        
        # Use CircleMarker with size based on photo count
        folium.CircleMarker(
            location=[user_row['lat'], user_row['long']],
            radius=radius,
            popup=folium.Popup(popup_html, max_width=350),
            color=color,
            fill=True,
            fillColor=color,
            fillOpacity=0.6,
            weight=2
        ).add_to(marker_clusters[user_row['year']])
    
    # Add POI markers to the POI feature group
    for poi_name, poi_data in POI.items():
        folium.Marker(
            location=[poi_data["lat"], poi_data["long"]],
            popup=f"<strong>{poi_name}</strong>",
            icon=folium.Icon(color='red', icon='map-marker-alt', prefix='fa')
        ).add_to(poi_group)
        
        # Add circle showing 200m radius
        folium.Circle(
            location=[poi_data["lat"], poi_data["long"]],
            radius=200,
            color='red',
            fill=True,
            fill_opacity=0.1,
            popup=f"{poi_name} - 200m radius"
        ).add_to(poi_group)

    # Add layer control
    folium.LayerControl(collapsed=False).add_to(my_map)
    
    # Add custom time slider control
    # Convert all_periods to list of strings for JSON
    periods_json = json.dumps([str(p) for p in all_periods])
    layer_ids_json = json.dumps(layer_ids)
    
    time_slider_html = f"""
    <div id="time-slider-container" style="
        position: fixed;
        bottom: 50px;
        left: 50%;
        transform: translateX(-50%);
        z-index: 1000;
        background: white;
        padding: 15px 25px;
        border-radius: 10px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.3);
        min-width: 400px;
    ">
        <div style="text-align: center; margin-bottom: 10px;">
            <strong id="current-period" style="font-size: 18px;">Loading...</strong>
        </div>
        <input type="range" id="time-slider" 
               min="0" max="{len(all_periods) - 1}" 
               value="{len(all_periods) - 1}" 
               step="1"
               style="width: 100%; cursor: pointer;">
        <div style="display: flex; justify-content: space-between; font-size: 14px; color: #666;">
            <span><strong>{all_periods[0]}</strong></span>
            <span><strong>{all_periods[-1]}</strong></span>
        </div>
        <div style="text-align: center; margin-top: 10px;">
            <button id="play-btn" style="
                padding: 5px 15px;
                cursor: pointer;
                border: none;
                background: #4CAF50;
                color: white;
                border-radius: 5px;
                font-size: 14px;
            ">▶ Play</button>
        </div>
    </div>
    
    <script>
        var periods = {periods_json};
        var layerIds = {layer_ids_json};
        var slider = document.getElementById('time-slider');
        var currentPeriodLabel = document.getElementById('current-period');
        var playBtn = document.getElementById('play-btn');
        var isPlaying = false;
        var playInterval = null;
        var timeoutId = null;
        
        // Wait for the map to be fully loaded
        function waitForMap(callback, maxAttempts = 50) {{
            var attempts = 0;
            var checkInterval = setInterval(function() {{
                // Look for the Leaflet map object
                var maps = document.querySelectorAll('.folium-map');
                if (maps.length > 0 && typeof window.maps !== 'undefined' || attempts > maxAttempts) {{
                    clearInterval(checkInterval);
                    callback();
                }}
                attempts++;
            }}, 100);
        }}
        
        function updateVisiblePeriod(index) {{
            var selectedPeriod = periods[index];
            currentPeriodLabel.textContent = selectedPeriod;
            
            // Find the layer control and manipulate it
            var layerControl = document.querySelector('.leaflet-control-layers-overlays');
            if (layerControl) {{
                var labels = layerControl.querySelectorAll('label');
                var changedAny = false;
                
                labels.forEach(function(label) {{
                    var input = label.querySelector('input[type="checkbox"]');
                    var spanText = label.querySelector('span');
                    
                    if (spanText && input) {{
                        var layerName = spanText.textContent.trim();
                        
                        // Check if this is a time period layer
                        if (periods.includes(layerName)) {{
                            var shouldBeChecked = (layerName === selectedPeriod);
                            var isChecked = input.checked;
                            
                            if (shouldBeChecked !== isChecked) {{
                                // Trigger a click event to toggle the layer
                                input.click();
                                changedAny = true;
                            }}
                        }}
                    }}
                }});
                
                console.log('Updated to period:', selectedPeriod, 'Changed layers:', changedAny);
            }} else {{
                console.log('Layer control not found');
            }}
        }}
        
        slider.addEventListener('input', function() {{
            updateVisiblePeriod(parseInt(this.value));
        }});
        
        playBtn.addEventListener('click', function() {{
            if (isPlaying) {{
                // Stop playing
                clearInterval(playInterval);
                playBtn.textContent = '▶ Play';
                playBtn.style.background = '#4CAF50';
                isPlaying = false;
            }} else {{
                // Start playing
                playBtn.textContent = '⏸ Pause';
                playBtn.style.background = '#FF9800';
                isPlaying = true;
                
                playInterval = setInterval(function() {{
                    var currentValue = parseInt(slider.value);
                    if (currentValue < periods.length - 1) {{
                        slider.value = currentValue + 1;
                        updateVisiblePeriod(currentValue + 1);
                    }} else {{
                        // Loop back to start
                        slider.value = 0;
                        updateVisiblePeriod(0);
                    }}
                }}, 1500);  // Change period every 1.5 seconds
            }}
        }});
        
        // Initialize after the map loads
        waitForMap(function() {{
            setTimeout(function() {{
                console.log('Initializing slider with periods:', periods);
                updateVisiblePeriod(periods.length - 1);
            }}, 1000);
        }});
    </script>
    """
    
    # my_map.get_root().html.add_child(folium.Element(time_slider_html))
    
    # Save and open the map
    output_file = "vk_photos_perm_heatmap.html"
    my_map.save(output_file)
    print(f"\nHeatmap saved as {output_file}")
    webbrowser.open('file://' + os.path.realpath(output_file))


if __name__ == "__main__":
    # Create visualization with all photos within 1000 meters of POIs
    create_heatmap_vk("vk_photos_perm_historical.csv", sample_size=1000, distance_threshold_meters=300)

