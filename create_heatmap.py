import pandas as pd
import folium
from folium.plugins import HeatMap, MarkerCluster
import webbrowser
import os
import math

from datetime import datetime

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


def create_heatmap(csv_file, sample_size=2000, distance_threshold=0.001, has_classes=False):
    chunk_size = 10000
    all_chunks = []
    
    if has_classes:
        cols = ['lat', 'long', 'distance','text', 'id', 'link', 'date', 'owner_id', 'class']
    else:
        cols = ['lat', 'long', 'distance','text', 'id', 'link', 'date', 'owner_id']

    for chunk in pd.read_csv(csv_file, usecols=cols, chunksize=chunk_size):
        chunk = chunk.dropna(subset=['lat', 'long'])
        chunk['distance_to_poi'] = chunk.apply(lambda row: get_min_distance_to_poi(row['lat'], row['long']), axis=1)
        chunk = chunk[chunk['distance_to_poi'] < distance_threshold]
        all_chunks.append(chunk)
        
        if sum(len(c) for c in all_chunks) >= sample_size:
            break
            
    df = pd.concat(all_chunks)
    if len(df) > sample_size:
        df = df.sample(sample_size, random_state=42)
    
    map_center = [df['lat'].mean(), df['long'].mean()]
    my_map = folium.Map(location=map_center, zoom_start=15, tiles='cartodbpositron')

    # colors_by_class = {
    #     "service": "pink",
    #     "product": "pink",
    #     "selfie": "blue",
    #     "touristic attraction / city view": "green",
    #     "event": "orange",
    #     "personal memory": "blue"
    # }
    texts = ["commercial service (beauty salon, hairdresser, flower shop)", "product (clothes, book, toy, handmade item, etc.)", \
         "selfie or a portrait of a person",\
         "touristic attraction or city view, architecture, building, etc.",
         "parks, nature, green, water, etc.",
         "public event, sports event, or a group of people", 
         "personal memory"]

    colors_by_class = {
        "commercial service (beauty salon, hairdresser, flower shop)": "pink",
        "product (clothes, book, toy, handmade item, etc.)": "pink",
        "selfie or a portrait of a person": "blue",
        "touristic attraction or city view, architecture, building, etc.": "lightgray",
        "parks, nature, green, water, etc.": "green",
        "public event, sports event, or a group of people": "orange",
        "personal memory": "lightblue",
    }

    # Create feature groups for each class (for toggling)
    feature_groups = {}
    for class_name in df['class'].unique():
        feature_groups[class_name] = folium.FeatureGroup(name=f"{class_name}", show=True).add_to(my_map)
    
    # Add a feature group for POIs
    poi_group = folium.FeatureGroup(name="Points of Interest", show=True).add_to(my_map)
    
    # Create marker clusters within each feature group
    marker_clusters = {}
    for class_name in df['class'].unique():
        color = colors_by_class[class_name]
        icon_function = f"""
            function(cluster) {{
                return L.divIcon({{
                    html: '<div style="background-color: {color}"><span>' + cluster.getChildCount() + '</span></div>',
                    className: 'marker-cluster',
                    iconSize: new L.Point(40, 40)
                }});
            }}
        """
        marker_clusters[class_name] = MarkerCluster(
            icon_create_function=icon_function
        ).add_to(feature_groups[class_name])

    # Add heatmaps to feature groups
    for class_name in df['class'].unique():
        heat_data = [[row['lat'], row['long']] for _, row in df[df['class'] == class_name].iterrows()]
        color = colors_by_class[class_name]
        # Create a gradient from transparent to the class color
        gradient = {0: 'transparent', 0.2: color, 1: color}
        HeatMap(
            heat_data, 
            min_opacity=0.5, 
            max_opacity=0.85, 
            radius=10, 
            gradient=gradient
        ).add_to(feature_groups[class_name])

    # Add markers to their respective clusters
    for _, row in df.sample(min(300, len(df))).iterrows():
        popup_html = f"""
        <div style="width:300px">
            <img src="{row['link']}" style="width: 100%; height: 100%;">
            <p>{row['text'] if not pd.isna(row['text']) else 'No description'}</p>
            <p>{datetime.fromtimestamp(row['date'])}, {row['owner_id']}</p>
        </div>
        """
        # select color based on class if available
        if has_classes:
            popup_html += f"<p>{row['class']}</p>"
            color = colors_by_class[row['class']]
        else:
            color = 'blue'
        folium.Marker(
            location=[row['lat'], row['long']],
            popup=folium.Popup(popup_html, max_width=300),
            icon=folium.Icon(color=color, icon='camera', prefix='fa')
        ).add_to(marker_clusters[row['class']])
    
    # Add POI markers to the POI feature group
    for poi in POI:
        folium.Marker(
            location=[POI[poi]["lat"], POI[poi]["long"]],
            popup=poi,
            icon=folium.Icon(color='red', icon='map-marker-alt', prefix='fa')
        ).add_to(poi_group)

    # Add layer control to toggle visibility
    folium.LayerControl(collapsed=False).add_to(my_map)

    # Save the map as an HTML file
    output_file = "photo_heatmap.html"
    my_map.save(output_file)
    print(f"Heatmap saved as {output_file}")
    
    # Open the map in the default web browser
    webbrowser.open('file://' + os.path.realpath(output_file))

if __name__ == "__main__":
    create_heatmap("photos_with_classes.csv", 1000, 0.1, has_classes=True)