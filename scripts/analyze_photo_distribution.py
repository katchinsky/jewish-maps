import pandas as pd
from pandas.api.types import is_bool_dtype
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime


def filter_inside_poi_area(df: pd.DataFrame, column: str = "inside_poi_area") -> pd.DataFrame:
    if column not in df.columns:
        print(f"Warning: column '{column}' not found. Skipping spatial filtering.")
        return df

    series = df[column]
    if is_bool_dtype(series):
        mask = series.fillna(False)
    else:
        normalized = (
            series.fillna("")
            .astype(str)
            .str.strip()
            .str.lower()
        )
        mask = normalized.isin({"true", "1", "yes"})

    filtered = df[mask].copy()
    dropped = len(df) - len(filtered)
    print(f"Filtered out {dropped} rows outside POI visibility ({column}).")
    if filtered.empty:
        print("Warning: no rows remain after filtering. Check the input dataset.")
    return filtered

# Set style for better-looking plots
sns.set_style("whitegrid")
plt.rcParams['figure.figsize'] = (14, 8)

def analyze_photo_distribution(csv_file, distance_threshold_meters=300):
    """
    Analyze and visualize the distribution of photos by year and POI
    
    Args:
        csv_file: Path to the CSV file with VK photos
        distance_threshold_meters: Maximum distance from POI in meters to include photos
    """
    # Read the CSV file
    df = pd.read_csv(csv_file)
    df = filter_inside_poi_area(df)
    
    # Drop rows without coordinates
    df = df.dropna(subset=['lat', 'long'])
    
    # Filter by distance threshold
    df = df[df['distance_meters'] < distance_threshold_meters]
    
    # Add time-based columns for filtering
    df['datetime'] = pd.to_datetime(df['date'], unit='s')
    df['year'] = df['datetime'].dt.year
    
    print(f"Total photos analyzed: {len(df)}")
    print(f"Distance threshold: {distance_threshold_meters} meters")
    print(f"Year range: {df['year'].min()} - {df['year'].max()}")
    print(f"\nTotal photos by POI:")
    print(df['poi_name'].value_counts())
    
    # Group by year and POI
    distribution = df.groupby(['year', 'poi_name']).size().reset_index(name='photo_count')
    
    # Create a pivot table for easier plotting
    pivot_data = distribution.pivot(index='year', columns='poi_name', values='photo_count').fillna(0)
    
    print(f"\nPhotos by year and POI:")
    print(pivot_data)
    
    # Create figure with multiple subplots
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle(f'Photo Distribution Analysis (within {distance_threshold_meters}m of POIs)', 
                 fontsize=16, fontweight='bold')
    
    # 1. Stacked bar chart
    ax1 = axes[0, 0]
    pivot_data.plot(kind='bar', stacked=True, ax=ax1, 
                    color=['#3498db', '#9b59b6', '#e67e22'])
    ax1.set_title('Stacked Bar Chart: Photos by Year and POI', fontsize=12, fontweight='bold')
    ax1.set_xlabel('Year', fontsize=11)
    ax1.set_ylabel('Number of Photos', fontsize=11)
    ax1.legend(title='POI', bbox_to_anchor=(1.05, 1), loc='upper left')
    ax1.tick_params(axis='x', rotation=45)
    ax1.grid(axis='y', alpha=0.3)
    
    # 2. Grouped bar chart
    ax2 = axes[0, 1]
    pivot_data.plot(kind='bar', ax=ax2, 
                    color=['#3498db', '#9b59b6', '#e67e22'])
    ax2.set_title('Grouped Bar Chart: Photos by Year and POI', fontsize=12, fontweight='bold')
    ax2.set_xlabel('Year', fontsize=11)
    ax2.set_ylabel('Number of Photos', fontsize=11)
    ax2.legend(title='POI', bbox_to_anchor=(1.05, 1), loc='upper left')
    ax2.tick_params(axis='x', rotation=45)
    ax2.grid(axis='y', alpha=0.3)
    
    # 3. Line chart
    ax3 = axes[1, 0]
    for column in pivot_data.columns:
        ax3.plot(pivot_data.index, pivot_data[column], marker='o', 
                linewidth=2, markersize=6, label=column)
    ax3.set_title('Trend Line: Photos by Year and POI', fontsize=12, fontweight='bold')
    ax3.set_xlabel('Year', fontsize=11)
    ax3.set_ylabel('Number of Photos', fontsize=11)
    ax3.legend(title='POI', bbox_to_anchor=(1.05, 1), loc='upper left')
    ax3.grid(True, alpha=0.3)
    ax3.set_xticks(pivot_data.index)
    ax3.tick_params(axis='x', rotation=45)
    
    # 4. Heatmap
    ax4 = axes[1, 1]
    sns.heatmap(pivot_data.T, annot=True, fmt='.0f', cmap='YlOrRd', 
                cbar_kws={'label': 'Number of Photos'}, ax=ax4)
    ax4.set_title('Heatmap: Photos by Year and POI', fontsize=12, fontweight='bold')
    ax4.set_xlabel('Year', fontsize=11)
    ax4.set_ylabel('POI', fontsize=11)
    
    plt.tight_layout()
    
    # Save the figure
    output_file = 'photo_distribution_analysis.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"\nGraph saved as {output_file}")
    
    # Show the plot
    plt.show()
    
    # Additional statistics
    print("\n" + "="*60)
    print("DETAILED STATISTICS")
    print("="*60)
    
    # Photos per year
    print("\nTotal photos per year:")
    yearly_totals = pivot_data.sum(axis=1).sort_index()
    for year, count in yearly_totals.items():
        print(f"  {year}: {int(count)} photos")
    
    # Photos per POI
    print("\nTotal photos per POI:")
    poi_totals = pivot_data.sum(axis=0).sort_values(ascending=False)
    for poi, count in poi_totals.items():
        print(f"  {poi}: {int(count)} photos")
    
    # Year with most photos
    max_year = yearly_totals.idxmax()
    max_count = yearly_totals.max()
    print(f"\nYear with most photos: {max_year} ({int(max_count)} photos)")
    
    # Most active POI
    most_active_poi = poi_totals.idxmax()
    most_active_count = poi_totals.max()
    print(f"Most photographed POI: {most_active_poi} ({int(most_active_count)} photos)")
    
    # Growth analysis
    print("\nYear-over-year growth:")
    for i in range(1, len(yearly_totals)):
        prev_year = yearly_totals.index[i-1]
        curr_year = yearly_totals.index[i]
        prev_count = yearly_totals.iloc[i-1]
        curr_count = yearly_totals.iloc[i]
        
        if prev_count > 0:
            growth = ((curr_count - prev_count) / prev_count) * 100
            print(f"  {prev_year} → {curr_year}: {growth:+.1f}% ({int(prev_count)} → {int(curr_count)})")
        else:
            print(f"  {prev_year} → {curr_year}: N/A (no photos in {prev_year})")
    
    return pivot_data


if __name__ == "__main__":
    # Analyze with the same threshold as the heatmap visualization
    analyze_photo_distribution("data/vk_photos_perm_historical_with_polygons.csv", distance_threshold_meters=100)





