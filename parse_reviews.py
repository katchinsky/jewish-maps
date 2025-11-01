#!/usr/bin/env python3
"""
Script to parse user reviews from HTML files in the data folder.
Supports multiple map services: Yandex Maps, Google Maps, 2GIS.
"""

import os
import csv
import re
from pathlib import Path
from bs4 import BeautifulSoup
from datetime import datetime
import json


class ReviewParser:
    """Base class for parsing reviews from different map services."""
    
    def __init__(self, html_content, filename):
        self.soup = BeautifulSoup(html_content, 'html.parser')
        self.filename = filename
        self.reviews = []
    
    def parse(self):
        """Parse reviews from HTML. To be implemented by subclasses."""
        raise NotImplementedError
    
    def get_source(self):
        """Determine the source/platform from filename."""
        filename_lower = self.filename.lower()
        if 'yandex' in filename_lower or 'яндекс' in filename_lower:
            return 'Yandex Maps'
        elif 'google' in filename_lower:
            return 'Google Maps'
        elif '2gis' in filename_lower or '2гис' in filename_lower:
            return '2GIS'
        else:
            return 'Unknown'


class YandexMapsParser(ReviewParser):
    """Parser for Yandex Maps HTML files."""
    
    def parse(self):
        """Parse Yandex Maps reviews using schema.org markup."""
        # Try to find the business name/location
        location = self.extract_location()
        
        # Find review elements using schema.org markup
        review_containers = self.soup.find_all('div', class_='business-review-view', itemprop='review')
        
        print(f"Found {len(review_containers)} reviews in {self.filename}")
        
        seen_reviews = set()  # Track unique reviews to avoid duplicates
        
        for container in review_containers:
            review_data = self.extract_yandex_review(container)
            
            # Create a unique key from text to detect duplicates
            if review_data and review_data.get('text'):
                review_key = (review_data.get('text', ''), review_data.get('username', ''))
                
                # Skip placeholder reviews and duplicates
                if (review_data['text'] not in ['Оцените это место', 'Оцените это место...'] and
                    review_key not in seen_reviews):
                    
                    review_data['location'] = location
                    review_data['source'] = 'Yandex Maps'
                    review_data['filename'] = self.filename
                    self.reviews.append(review_data)
                    seen_reviews.add(review_key)
        
        return self.reviews
    
    def extract_location(self):
        """Extract location/business name from page."""
        # Try h1 first (most reliable)
        h1 = self.soup.find('h1')
        if h1:
            return h1.get_text(strip=True)
        
        # Try card-title-view
        card_title = self.soup.find(class_=lambda c: c and 'card-title-view__title' in str(c))
        if card_title:
            return card_title.get_text(strip=True)
        
        # Try meta tags
        meta_title = self.soup.find('meta', property='og:title')
        if meta_title:
            return meta_title.get('content', '').split('—')[0].strip()
        
        title = self.soup.find('title')
        if title:
            return title.get_text().split('—')[0].strip()
        
        # Fallback: Try to extract from filename
        location = self.extract_location_from_filename()
        if location:
            return location
        
        return 'Unknown Location'
    
    def extract_location_from_filename(self):
        """Extract location from filename as fallback."""
        # Remove extension and common prefixes
        name = self.filename.replace('.html', '')
        name = re.sub(r'^(yandex|google|2gis)-', '', name, flags=re.IGNORECASE)
        
        # Common location names mapping
        location_map = {
            'cdek': 'CDEK',
            'sinagogue': 'Synagogue',
            'khabar': 'Khabar Lyubavich Or Avner',
            'twins': 'Twins',
        }
        
        for key, value in location_map.items():
            if key in name.lower():
                return value
        
        # Capitalize and clean up
        if name and name != 'Unknown Location':
            return name.replace('-', ' ').replace('_', ' ').title()
        
        return None
    
    def extract_yandex_review(self, container):
        """Extract review data from Yandex container using schema.org markup."""
        review = {}
        
        # Extract text using schema.org
        text_elem = container.find(itemprop='reviewBody')
        if text_elem:
            review['text'] = text_elem.get_text(strip=True)
        
        # Extract username using schema.org
        author_elem = container.find(itemprop='name')
        if author_elem:
            review['username'] = author_elem.get_text(strip=True)
        
        # Extract date using schema.org
        date_elem = container.find('meta', itemprop='datePublished')
        if date_elem:
            date_str = date_elem.get('content', '')
            # Convert ISO format to readable format
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                review['date'] = dt.strftime('%Y-%m-%d')
            except:
                review['date'] = date_str
        else:
            # Fallback to visible date text
            date_text = container.find(class_=lambda c: c and 'business-review-view__date' in str(c))
            if date_text:
                review['date'] = date_text.get_text(strip=True)
        
        # Extract rating using schema.org
        rating_elem = container.find('meta', itemprop='ratingValue')
        if rating_elem:
            review['rating'] = str(int(float(rating_elem.get('content', ''))))
        
        return review


class GoogleMapsParser(ReviewParser):
    """Parser for Google Maps HTML files."""
    
    def parse(self):
        """Parse Google Maps reviews."""
        location = self.extract_location()
        
        # Google Maps uses class jftiEf fontBodyMedium for review containers
        review_containers = self.soup.find_all('div', class_='jftiEf fontBodyMedium', attrs={'data-review-id': True})
        
        print(f"Found {len(review_containers)} reviews in {self.filename}")
        
        seen_reviews = set()  # Track unique reviews to avoid duplicates
        
        for container in review_containers:
            review_data = self.extract_google_review(container)
            
            # Create a unique key from text to detect duplicates
            if review_data and review_data.get('text'):
                review_key = (review_data.get('text', ''), review_data.get('username', ''))
                
                # Skip duplicates
                if review_key not in seen_reviews:
                    review_data['location'] = location
                    review_data['source'] = 'Google Maps'
                    review_data['filename'] = self.filename
                    self.reviews.append(review_data)
                    seen_reviews.add(review_key)
        
        return self.reviews
    
    def extract_location(self):
        """Extract location from Google Maps page."""
        # Try h1 first
        h1 = self.soup.find('h1')
        if h1:
            return h1.get_text(strip=True)
        
        # Try aria-label on main section
        main = self.soup.find('div', attrs={'role': 'main', 'aria-label': True})
        if main:
            location = main.get('aria-label', '')
            if location and location != 'main':
                return location
        
        # Try meta tags
        meta_title = self.soup.find('meta', property='og:title')
        if meta_title:
            return meta_title.get('content', '').split('-')[0].strip()
        
        title_tag = self.soup.find('title')
        if title_tag:
            return title_tag.get_text().split('-')[0].strip()
        
        # Fallback: Try to extract from filename
        location = self.extract_location_from_filename()
        if location:
            return location
        
        return 'Unknown Location'
    
    def extract_location_from_filename(self):
        """Extract location from filename as fallback."""
        # Remove extension and common prefixes
        name = self.filename.replace('.html', '')
        name = re.sub(r'^(yandex|google|2gis)-', '', name, flags=re.IGNORECASE)
        
        # Common location names mapping
        location_map = {
            'synagogue': 'Synagogue',
            'sinagogue': 'Synagogue',
            'khabar': 'Khabar Lyubavich Or Avner',
            'cdek': 'CDEK',
            'twins': 'Twins',
        }
        
        for key, value in location_map.items():
            if key in name.lower():
                return value
        
        # Capitalize and clean up
        if name and name != 'Unknown Location':
            return name.replace('-', ' ').replace('_', ' ').title()
        
        return None
    
    def extract_google_review(self, container):
        """Extract review data from Google Maps container."""
        review = {}
        
        # Extract text from div.MyEned > span.wiI7pd
        text_container = container.find('div', class_='MyEned')
        if text_container:
            text_span = text_container.find('span', class_='wiI7pd')
            if text_span:
                review['text'] = text_span.get_text(strip=True)
        
        # Extract username from div.d4r55.fontTitleMedium
        author_elem = container.find('div', class_='d4r55 fontTitleMedium')
        if author_elem:
            review['username'] = author_elem.get_text(strip=True)
        else:
            # Fallback: try aria-label on the container
            aria_label = container.get('aria-label', '')
            if aria_label:
                review['username'] = aria_label
        
        # Extract date from span.rsqaWe
        date_elem = container.find('span', class_='rsqaWe')
        if date_elem:
            date_text = date_elem.get_text(strip=True)
            review['date'] = self.parse_google_date(date_text)
        
        # Extract rating - count filled stars
        # Look for span.kvMYJc with role="img"
        rating_container = container.find('span', class_='kvMYJc', attrs={'role': 'img'})
        if rating_container:
            # Count filled stars (class contains 'elGi1d')
            filled_stars = rating_container.find_all('span', class_=lambda c: c and 'elGi1d' in c)
            if filled_stars:
                review['rating'] = str(len(filled_stars))
            else:
                # Fallback: try to extract from aria-label
                aria_label = rating_container.get('aria-label', '')
                rating_match = re.search(r'(\d+)\s+star', aria_label, re.I)
                if rating_match:
                    review['rating'] = rating_match.group(1)
        
        return review
    
    def parse_google_date(self, date_str):
        """Parse Google Maps date format."""
        # Google uses relative dates like "3 years ago", "6 months ago"
        # We'll keep them as-is for now, but could convert to approximate dates
        
        # Remove "Edited " prefix if present
        date_str = date_str.replace('Edited ', '').strip()
        
        # Try to convert relative dates to approximate dates
        from datetime import datetime, timedelta
        import re
        
        now = datetime.now()
        
        # Match patterns like "X years ago", "X months ago", "X days ago"
        year_match = re.search(r'(\d+)\s+year', date_str)
        month_match = re.search(r'(\d+)\s+month', date_str)
        week_match = re.search(r'(\d+)\s+week', date_str)
        day_match = re.search(r'(\d+)\s+day', date_str)
        
        if year_match:
            years = int(year_match.group(1))
            approx_date = now - timedelta(days=years*365)
            return approx_date.strftime('%Y-%m-%d')
        elif month_match:
            months = int(month_match.group(1))
            approx_date = now - timedelta(days=months*30)
            return approx_date.strftime('%Y-%m-%d')
        elif week_match:
            weeks = int(week_match.group(1))
            approx_date = now - timedelta(weeks=weeks)
            return approx_date.strftime('%Y-%m-%d')
        elif day_match:
            days = int(day_match.group(1))
            approx_date = now - timedelta(days=days)
            return approx_date.strftime('%Y-%m-%d')
        
        # Return as-is if we can't parse it
        return date_str


class TwoGISParser(ReviewParser):
    """Parser for 2GIS HTML files."""
    
    def parse(self):
        """Parse 2GIS reviews."""
        location = self.extract_location()
        
        # 2GIS uses class _1k5soqfl for review containers
        review_containers = self.soup.find_all('div', class_='_1k5soqfl')
        
        print(f"Found {len(review_containers)} reviews in {self.filename}")
        
        seen_reviews = set()  # Track unique reviews to avoid duplicates
        
        for container in review_containers:
            review_data = self.extract_2gis_review(container)
            
            # Create a unique key from text to detect duplicates
            if review_data and review_data.get('text'):
                review_key = (review_data.get('text', ''), review_data.get('username', ''))
                
                # Skip duplicates and very short reviews
                if review_key not in seen_reviews and len(review_data['text']) > 5:
                    review_data['location'] = location
                    review_data['source'] = '2GIS'
                    review_data['filename'] = self.filename
                    self.reviews.append(review_data)
                    seen_reviews.add(review_key)
        
        return self.reviews
    
    def extract_location(self):
        """Extract location from 2GIS page."""
        # Try h1 with class _1x89xo5
        h1 = self.soup.find('h1', class_='_1x89xo5')
        if h1:
            return h1.get_text(strip=True)
        
        # Try any h1
        h1 = self.soup.find('h1')
        if h1:
            return h1.get_text(strip=True)
        
        # Try meta tags
        meta_title = self.soup.find('meta', property='og:title')
        if meta_title:
            return meta_title.get('content', '').split('—')[0].strip()
        
        title_tag = self.soup.find('title')
        if title_tag:
            return title_tag.get_text().split('—')[0].strip()
        
        # Fallback: Try to extract from filename
        location = self.extract_location_from_filename()
        if location:
            return location
        
        return 'Unknown Location'
    
    def extract_location_from_filename(self):
        """Extract location from filename as fallback."""
        # Remove extension and common prefixes
        name = self.filename.replace('.html', '')
        name = re.sub(r'^(yandex|google|2gis)-', '', name, flags=re.IGNORECASE)
        
        # Common location names mapping
        location_map = {
            'khabar': 'Khabar Lyubavich Or Avner',
            'sinagogue': 'Synagogue',
            'cdek': 'CDEK',
            'twins': 'Twins',
        }
        
        for key, value in location_map.items():
            if key in name.lower():
                return value
        
        # Capitalize and clean up
        if name and name != 'Unknown Location':
            return name.replace('-', ' ').replace('_', ' ').title()
        
        return None
    
    def extract_2gis_review(self, container):
        """Extract review data from 2GIS container."""
        review = {}
        
        # Extract text from div._49x36f > a._1msln3t
        text_elem = container.find('div', class_='_49x36f')
        if text_elem:
            link = text_elem.find('a', class_='_1msln3t')
            if link:
                review['text'] = link.get_text(strip=True)
        
        # Extract username from span._16s5yj36 with title attribute
        author_elem = container.find('span', class_='_16s5yj36')
        if author_elem:
            # The title attribute has the full username
            username = author_elem.get('title', author_elem.get_text(strip=True))
            review['username'] = username
        
        # Extract date from div._a5f6uz
        date_elem = container.find('div', class_='_a5f6uz')
        if date_elem:
            date_text = date_elem.get_text(strip=True)
            # Remove ", отредактирован" if present
            date_text = date_text.replace(', отредактирован', '')
            review['date'] = self.parse_2gis_date(date_text)
        
        # Extract rating - count filled stars in div._1m0m6z5
        rating_container = container.find('div', class_='_1m0m6z5')
        if rating_container:
            # Count SVG elements with fill="#ffb81c" (filled stars)
            filled_stars = rating_container.find_all('svg', attrs={'fill': '#ffb81c'})
            if filled_stars:
                review['rating'] = str(len(filled_stars))
        
        return review
    
    def parse_2gis_date(self, date_str):
        """Parse 2GIS date format to YYYY-MM-DD."""
        # 2GIS uses Russian dates like "2 августа 2024" or "6 мая 2023"
        months = {
            'января': '01', 'февраля': '02', 'марта': '03', 'апреля': '04',
            'мая': '05', 'июня': '06', 'июля': '07', 'августа': '08',
            'сентября': '09', 'октября': '10', 'ноября': '11', 'декабря': '12'
        }
        
        try:
            # Parse "2 августа 2024" format
            parts = date_str.split()
            if len(parts) >= 3:
                day = parts[0]
                month_name = parts[1]
                year = parts[2]
                
                if month_name in months:
                    month = months[month_name]
                    return f"{year}-{month}-{day.zfill(2)}"
        except:
            pass
        
        return date_str


def get_parser(filename, html_content):
    """Factory function to get appropriate parser based on filename."""
    filename_lower = filename.lower()
    
    if 'yandex' in filename_lower or 'яндекс' in filename_lower:
        return YandexMapsParser(html_content, filename)
    elif 'google' in filename_lower:
        return GoogleMapsParser(html_content, filename)
    elif '2gis' in filename_lower or '2гис' in filename_lower:
        return TwoGISParser(html_content, filename)
    else:
        # Default to Yandex parser
        return YandexMapsParser(html_content, filename)


def parse_all_html_files(data_dir='data'):
    """Parse all HTML files in the data directory."""
    all_reviews = []
    data_path = Path(data_dir)
    
    if not data_path.exists():
        print(f"Error: Directory '{data_dir}' not found")
        return all_reviews
    
    html_files = list(data_path.glob('*.html'))
    
    if not html_files:
        print(f"No HTML files found in '{data_dir}'")
        return all_reviews
    
    print(f"\nProcessing {len(html_files)} HTML files...")
    print("=" * 60)
    
    for html_file in html_files:
        print(f"\nProcessing: {html_file.name}")
        
        try:
            with open(html_file, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            parser = get_parser(html_file.name, html_content)
            reviews = parser.parse()
            
            print(f"  ✓ Extracted {len(reviews)} reviews")
            all_reviews.extend(reviews)
            
        except Exception as e:
            print(f"  ✗ Error processing {html_file.name}: {e}")
    
    print("\n" + "=" * 60)
    print(f"Total reviews extracted: {len(all_reviews)}")
    
    return all_reviews


def save_to_csv(reviews, output_file='reviews.csv'):
    """Save reviews to CSV file."""
    if not reviews:
        print("No reviews to save")
        return
    
    # Define all possible fields
    fieldnames = [
        'location',
        'username', 
        'date',
        'rating',
        'text',
        'source',
        'filename'
    ]
    
    # Ensure all reviews have all fields
    for review in reviews:
        for field in fieldnames:
            if field not in review:
                review[field] = ''
    
    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(reviews)
    
    print(f"\n✓ Reviews saved to '{output_file}'")
    print(f"  Total rows: {len(reviews)}")
    
    # Print statistics
    print_statistics(reviews)


def print_statistics(reviews):
    """Print statistics about extracted reviews."""
    print("\n" + "=" * 60)
    print("Statistics:")
    print("=" * 60)
    
    # Reviews by location
    from collections import Counter
    locations = Counter(r['location'] for r in reviews)
    print("\nReviews by location:")
    for location, count in locations.most_common():
        print(f"  - {location}: {count} reviews")
    
    # Reviews by source
    sources = Counter(r['source'] for r in reviews)
    print("\nReviews by source:")
    for source, count in sources.most_common():
        print(f"  - {source}: {count} reviews")
    
    # Rating distribution
    ratings = [r['rating'] for r in reviews if r.get('rating')]
    if ratings:
        print("\nRating distribution:")
        rating_counts = Counter(ratings)
        for rating in sorted(rating_counts.keys()):
            count = rating_counts[rating]
            bar = '█' * int(count / len(reviews) * 50)
            print(f"  {rating}: {bar} ({count})")
        
        avg_rating = sum(float(r) for r in ratings) / len(ratings)
        print(f"\nAverage rating: {avg_rating:.2f}")
    
    # Date range
    dates = [r['date'] for r in reviews if r.get('date')]
    if dates:
        dates_sorted = sorted(dates)
        print(f"\nDate range: {dates_sorted[0]} to {dates_sorted[-1]}")


def main():
    """Main execution function."""
    print("=" * 60)
    print("Review Parser for Map Services")
    print("=" * 60)
    
    # Parse all HTML files
    reviews = parse_all_html_files('data')
    
    # Save to CSV
    if reviews:
        save_to_csv(reviews, 'reviews.csv')
        
        # Print sample reviews
        print("\n" + "=" * 60)
        print("Sample reviews:")
        print("=" * 60)
        for i, review in enumerate(reviews[:3], 1):
            print(f"\nReview {i}:")
            print(f"  Location: {review.get('location', 'N/A')}")
            print(f"  Username: {review.get('username', 'N/A')}")
            print(f"  Date: {review.get('date', 'N/A')}")
            print(f"  Rating: {review.get('rating', 'N/A')}")
            print(f"  Text: {review.get('text', 'N/A')[:100]}...")
            print(f"  Source: {review.get('source', 'N/A')}")
        
        print("\n" + "=" * 60)
        print("✓ Extraction completed successfully!")
        print("=" * 60)
    else:
        print("\n⚠ No reviews were extracted. The HTML files might have a different structure.")
        print("Please check the HTML files manually or provide a sample for debugging.")


if __name__ == '__main__':
    main()

