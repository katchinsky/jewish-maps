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


class YandexMapsJSONParser:
    """Parser for Yandex Maps JSON files (.json format)."""
    
    def __init__(self, json_content, filename):
        self.json_content = json_content
        self.filename = filename
        self.reviews = []
    
    def parse(self):
        """Parse Yandex Maps reviews from JSON."""
        try:
            data = json.loads(self.json_content)
            location = self.extract_location_from_filename()
            
            # Extract reviews from data.reviews array
            reviews_data = data.get('data', {}).get('reviews', [])
            
            print(f"Found {len(reviews_data)} reviews in {self.filename}")
            
            for review_data in reviews_data:
                # Extract basic review info
                review = {
                    'location': location,
                    'username': review_data.get('author', {}).get('name', ''),
                    'date': self.parse_yandex_date(review_data.get('updatedTime', '')),
                    'rating': str(review_data.get('rating', '')),
                    'text': review_data.get('text', ''),
                    'text_en': self.extract_english_translation(review_data),
                    'business_response': self.extract_business_response(review_data),
                    'source': 'Yandex Maps (JSON)',
                    'filename': self.filename
                }
                
                # Only add if we have actual review text
                if review['text'] and len(review['text']) > 5:
                    self.reviews.append(review)
            
            return self.reviews
            
        except Exception as e:
            print(f"  ✗ Error parsing Yandex JSON: {e}")
            return []
    
    def parse_yandex_date(self, date_str):
        """Parse Yandex date format (ISO 8601) to YYYY-MM-DD."""
        if not date_str:
            return ''
        try:
            # Parse ISO 8601 format like "2024-08-17T08:40:18.174Z"
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.strftime('%Y-%m-%d')
        except:
            return date_str
    
    def extract_english_translation(self, review_data):
        """Extract English translation if available."""
        translations = review_data.get('textTranslations', {})
        # Check for English translation
        if 'en' in translations:
            return translations['en']
        # If no English, return empty (we could also return other languages if needed)
        return ''
    
    def extract_business_response(self, review_data):
        """Extract business response/comment if available."""
        business_comment = review_data.get('businessComment', {})
        if business_comment:
            return business_comment.get('text', '')
        return ''
    
    def extract_location_from_filename(self):
        """Extract location from filename."""
        name = self.filename.replace('.json', '').replace('.txt', '').replace('.html', '')
        name = re.sub(r'^(yandex|google|2gis)-', '', name, flags=re.IGNORECASE)
        
        location_map = {
            'khabar': 'Ор Авнер Хабад',
            'synagogue': 'Центральная Пермская синагога',
            'sinagogue': 'Центральная Пермская синагога',
            'cdek': 'CDEK',
            'twins': 'Twins',
            'poke': 'ПокеРамен',
            'ryumochnaya': 'Рюмочная Парадная',
        }
        
        for key, value in location_map.items():
            if key in name.lower():
                return value
        
        if name and name != 'Unknown Location':
            return name.replace('-', ' ').replace('_', ' ').title()
        
        return 'Unknown Location'


class GoogleMapsJSONParser:
    """Parser for Google Maps JSON files (.txt format)."""
    
    def __init__(self, json_content, filename):
        self.json_content = json_content
        self.filename = filename
        self.reviews = []
    
    def parse(self):
        """Parse Google Maps reviews from JSON."""
        try:
            # Remove the )]}' prefix if present
            content = self.json_content
            if content.startswith(")]}'"):
                content = content[4:]
            
            data = json.loads(content)
            location = self.extract_location_from_filename()
            
            # Recursively find reviews in the JSON structure
            reviews_found = []
            self.find_reviews(data, reviews_found)
            
            print(f"Found {len(reviews_found)} reviews in {self.filename}")
            
            seen_reviews = set()
            for review_pair in reviews_found:
                russian_text = review_pair.get('russian', '')
                english_text = review_pair.get('english', '')
                
                if russian_text and len(russian_text) > 5:
                    review_key = russian_text
                    if review_key not in seen_reviews:
                        review_data = {
                            'location': location,
                            'username': '',  # Not available in JSON format
                            'date': '',  # Not available in JSON format
                            'rating': '',  # Not available in JSON format
                            'text': russian_text,
                            'text_en': english_text,  # English translation
                            'source': 'Google Maps (JSON)',
                            'filename': self.filename
                        }
                        self.reviews.append(review_data)
                        seen_reviews.add(review_key)
            
            return self.reviews
            
        except Exception as e:
            print(f"  ✗ Error parsing JSON: {e}")
            return []
    
    def find_reviews(self, obj, reviews):
        """Recursively find review texts in JSON structure."""
        if isinstance(obj, dict):
            for value in obj.values():
                self.find_reviews(value, reviews)
        elif isinstance(obj, list):
            # Check if this looks like a review array with bilingual text
            if (len(obj) == 2 and isinstance(obj[0], list) and isinstance(obj[1], list)):
                # Pattern: [["Russian text", null, [0, 151]], ["English text", null, [0, 156]]]
                if (len(obj[0]) >= 1 and isinstance(obj[0][0], str) and 
                    len(obj[1]) >= 1 and isinstance(obj[1][0], str)):
                    text_0 = obj[0][0]
                    text_1 = obj[1][0]
                    
                    # Determine which is Russian and which is English
                    if re.search(r'[а-яА-ЯёЁ]', text_0):
                        # text_0 is Russian, text_1 is English
                        reviews.append({
                            'russian': text_0,
                            'english': text_1
                        })
                        return  # Found a review, don't recurse further
                    elif re.search(r'[а-яА-ЯёЁ]', text_1):
                        # text_1 is Russian, text_0 is English
                        reviews.append({
                            'russian': text_1,
                            'english': text_0
                        })
                        return  # Found a review, don't recurse further
            
            # Continue recursing
            for item in obj:
                self.find_reviews(item, reviews)
    
    def extract_location_from_filename(self):
        """Extract location from filename."""
        name = self.filename.replace('.txt', '').replace('.html', '')
        name = re.sub(r'^(yandex|google|2gis)-', '', name, flags=re.IGNORECASE)
        
        location_map = {
            'khabar': 'Khabar Lyubavich Or Avner',
            'synagogue': 'Tsentral\'naya Permskaya Sinagoga',
            'sinagogue': 'Tsentral\'naya Permskaya Sinagoga',
            'cdek': 'CDEK',
            'twins': 'Twins',
            'poke': 'PokeRamen',
            'ryumochnaya': 'Ryumochnaya "Paradnaya"',
        }
        
        for key, value in location_map.items():
            if key in name.lower():
                return value
        
        if name and name != 'Unknown Location':
            return name.replace('-', ' ').replace('_', ' ').title()
        
        return 'Unknown Location'


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


def get_parser(filename, content):
    """Factory function to get appropriate parser based on filename and content."""
    filename_lower = filename.lower()
    
    # Check for JSON files first
    if filename.endswith('.json'):
        if 'yandex' in filename_lower or 'яндекс' in filename_lower:
            return YandexMapsJSONParser(content, filename)
    
    # Check for TXT files (Google Maps JSON format)
    if filename.endswith('.txt') and 'google' in filename_lower:
        return GoogleMapsJSONParser(content, filename)
    
    # HTML parsers
    if 'yandex' in filename_lower or 'яндекс' in filename_lower:
        return YandexMapsParser(content, filename)
    elif 'google' in filename_lower:
        return GoogleMapsParser(content, filename)
    elif '2gis' in filename_lower or '2гис' in filename_lower:
        return TwoGISParser(content, filename)
    else:
        # Default to Yandex parser
        return YandexMapsParser(content, filename)


def parse_all_html_files(data_dir='data'):
    """Parse all HTML, TXT, and JSON files in the data directory."""
    all_reviews = []
    data_path = Path(data_dir)
    
    if not data_path.exists():
        print(f"Error: Directory '{data_dir}' not found")
        return all_reviews
    
    # Find HTML, TXT, and JSON files
    html_files = list(data_path.glob('*.html'))
    txt_files = list(data_path.glob('*.txt'))
    json_files = list(data_path.glob('*.json'))
    all_files = html_files + txt_files + json_files
    
    if not all_files:
        print(f"No HTML, TXT, or JSON files found in '{data_dir}'")
        return all_reviews
    
    print(f"\nProcessing {len(all_files)} files ({len(html_files)} HTML, {len(txt_files)} TXT, {len(json_files)} JSON)...")
    print("=" * 60)
    
    for file_path in all_files:
        print(f"\nProcessing: {file_path.name}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            parser = get_parser(file_path.name, content)
            reviews = parser.parse()
            
            print(f"  ✓ Extracted {len(reviews)} reviews")
            all_reviews.extend(reviews)
            
        except Exception as e:
            print(f"  ✗ Error processing {file_path.name}: {e}")
    
    print("\n" + "=" * 60)
    print(f"Total reviews extracted: {len(all_reviews)}")
    
    return all_reviews


def normalize_location(location):
    """Normalize location names to group the same places together."""
    location_lower = location.lower()
    
    # PokeRamen group
    if 'poke' in location_lower or 'покерамен' in location_lower:
        return 'PokeRamen'
    
    # Paradnaya (Ryumochnaya) group
    if 'парадная' in location_lower or 'paradnaya' in location_lower or 'рюмочная' in location_lower or 'ryumochnaya' in location_lower:
        return 'Ryumochnaya Paradnaya'
    
    # Twins group
    if 'twins' in location_lower:
        return 'Twins'
    
    # CDEK group (including Vrmuse and Cdex which are CDEK locations)
    if 'cdek' in location_lower or 'cdex' in location_lower or 'сдэк' in location_lower or 'vrmuse' in location_lower:
        return 'CDEK'
    
    # Synagogue group
    if ('синагог' in location_lower or 'sinagog' in location_lower or 
        'иудейское религиозное общество' in location_lower):
        return 'Tsentral\'naya Permskaya Sinagoga'
    
    # Khabar/Or Avner group
    if ('khabar' in location_lower or 'хабад' in location_lower or 
        'авнер' in location_lower or 'avner' in location_lower or
        '25 октября' in location_lower or 'краснова' in location_lower or
        'средняя школа' in location_lower):
        return 'Or Avner Khabad'
    
    # ProBeauty group
    if 'probeauty' in location_lower or 'пробьюти' in location_lower:
        return 'ProBeauty'
    
    # If no match, return original location
    return location


def save_to_csv(reviews, output_file='reviews.csv'):
    """Save reviews to CSV file."""
    if not reviews:
        print("No reviews to save")
        return
    
    # Define all possible fields
    fieldnames = [
        'location',
        'location_normalized',  # Normalized location name for grouping
        'username', 
        'date',
        'rating',
        'text',
        'text_en',  # English translation (for JSON sources)
        'business_response',  # Business reply to review (for Yandex JSON)
        'source',
        'filename'
    ]
    
    # Ensure all reviews have all fields and normalize locations
    for review in reviews:
        # Add normalized location
        if 'location_normalized' not in review:
            review['location_normalized'] = normalize_location(review.get('location', ''))
        
        # Ensure all other fields exist
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
    
    # Reviews by normalized location
    from collections import Counter
    normalized_locations = Counter(r.get('location_normalized', r.get('location', '')) for r in reviews)
    print("\nReviews by normalized location:")
    for location, count in normalized_locations.most_common():
        print(f"  - {location}: {count} reviews")
    
    # Reviews by original location (for reference)
    locations = Counter(r['location'] for r in reviews)
    print("\nReviews by original location (detailed):")
    for location, count in locations.most_common():
        normalized = normalize_location(location)
        if normalized != location:
            print(f"  - {location}: {count} reviews → [{normalized}]")
        else:
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

