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
    
    df = pd.concat(all_chunks)
    print(df.count())
    map_center = [df['lat'].mean(), df['long'].mean()]
    my_map = folium.Map(location=map_center, zoom_start=15, tiles=None)
    my_map.add_child(folium.TileLayer('openstreetmap'))
    my_map.add_child(folium.TileLayer('cartodbpositron'))

    colors_by_class = {
        "event": "orange",
        "service ad": "pink",
        "product ad": "pink",
        "picture of a person: casual selfie or a portrait of a person": "lightblue",
        "picture of a person: a group of people, a family, a group of friends": "blue",
        "picture of a view (city)": "lightgray",
        "picture of a view (nature)": "green",
        "picture of an interior": "beige",
        "picture of a place of worship": "gray",
        "unknown": "white"
    }

    def get_color(class_name):
        short_class_name = class_name.split(':')[0]
        return colors_by_class.get(class_name, colors_by_class.get(short_class_name, 'white'))

    # Create feature groups for each class (for toggling)
    feature_groups = {}
    for class_name in df['class'].unique():
        feature_groups[class_name] = folium.FeatureGroup(name=f"{class_name}", show=True).add_to(my_map)
    
    # Add a feature group for POIs
    poi_group = folium.FeatureGroup(name="Points of Interest", show=True).add_to(my_map)
    
    # Create marker clusters within each feature group
    marker_clusters = {}
    for class_name in df['class'].unique():
        color = get_color(class_name)
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

        heat_data = [[row['lat'], row['long']] for _, row in df[df['class'] == class_name].iterrows()]
        gradient = {0: 'transparent', 0.2: color, 1: color}
        HeatMap(
            heat_data, 
            min_opacity=0.6, 
            max_opacity=0.9, 
            radius=10, 
            gradient=gradient
        ).add_to(feature_groups[class_name])

    # 1. Find all points within 200m of any POI
    poi_radius = 0.2 / 111
    def is_within_poi(lat, lon):
        for poi in POI.values():
            if get_distance(lat, lon, poi["lat"], poi["long"]) < 0.0015:  # 0.002 degrees ~ 200m
                return True
        return False

    df['in_poi_circle'] = df.apply(lambda row: is_within_poi(row['lat'], row['long']), axis=1)

    in_circle = df[df['in_poi_circle']]
    out_circle = df[~df['in_poi_circle']]

    # n_to_sample = max(0, sample_size - len(in_circle))
    n_to_sample = sample_size
    n_per_class = n_to_sample // len(df['class'].unique())
    sampled_out_circle = out_circle.groupby('class', group_keys=False).apply(
        lambda x: x.sample(min(len(x), n_per_class), random_state=42)
    )
    df_to_plot = pd.concat([in_circle, sampled_out_circle])

    for _, row in df_to_plot.iterrows():
        popup_html = f"""
        <div style="width:300px">
            <img src="{row['link']}" style="width: 100%; height: 100%;">
            <p>{row['text'] if not pd.isna(row['text']) else 'No description'}</p>
            <p>{datetime.fromtimestamp(row['date'])}, {row['owner_id']}</p>
        </div>
        """
        if has_classes:
            popup_html += f"<p>{row['class']}</p>"
            color = get_color(row['class']) or 'white'
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
        folium.Circle(
            location=[POI[poi]["lat"], POI[poi]["long"]],
            radius=200,
            color='red',
            fill=True,
            fill_opacity=0.1
        ).add_to(poi_group)

    folium.LayerControl(collapsed=False).add_to(my_map)
    output_file = "photo_heatmap.html"
    my_map.save(output_file)
    print(f"Heatmap saved as {output_file}")
    webbrowser.open('file://' + os.path.realpath(output_file))

if __name__ == "__main__":
    create_heatmap("photos_with_classes_and_probs.csv", 500, 0.1, has_classes=True)