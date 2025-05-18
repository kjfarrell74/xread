"""
Module for enhancing scraped social media posts with additional metadata.

This module provides functionality to process raw scraped social media posts
and enrich them with additional metadata such as normalized dates, image descriptions,
media flags, and engagement metrics placeholders.
"""

import re
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from urllib.parse import urlparse
from dateutil import parser
from PIL import Image
import pytesseract
import os

def enhance_post_json(data: dict) -> dict:
    """
    Enhance a scraped social media post JSON with additional metadata.
    
    This function takes a raw scraped social media post JSON and enriches it with:
    - Normalized date fields (ISO 8601 timestamps in UTC)
    - Image descriptions using heuristics and filename analysis
    - Media type flags (has_images, has_video, has_links)
    - Engagement metadata placeholders
    - Top-level research placeholders
    
    Args:
        data (dict): The original scraped post JSON containing main_post, replies, etc.
        
    Returns:
        dict: Enhanced post JSON with all original data preserved plus additional fields
        
    Example:
        >>> enhanced_data = enhance_post_json(original_data)
        >>> print(enhanced_data["main_post"]["date_iso"])  # ISO 8601 timestamp
        >>> print(enhanced_data["main_post"]["has_images"])  # Boolean flag
    """
    # Create a deep copy to avoid modifying the original
    enhanced_data = data.copy()
    
    # Process main post
    if "main_post" in enhanced_data:
        enhanced_data["main_post"] = enhance_post(enhanced_data["main_post"])
    
    # Process replies
    if "replies" in enhanced_data:
        enhanced_data["replies"] = [enhance_post(reply) for reply in enhanced_data["replies"]]
    
    # Add top-level placeholders
    enhanced_data.setdefault("research_questions", None)
    enhanced_data.setdefault("search_terms", None)
    enhanced_data.setdefault("summary_points", None)
    
    # Normalize scrape_date if present
    if "scrape_date" in enhanced_data:
        try:
            parsed_date = parser.parse(enhanced_data["scrape_date"])
            enhanced_data["scrape_date_iso"] = parsed_date.astimezone(timezone.utc).isoformat()
        except Exception as e:
            logging.warning(f"Could not parse scrape_date: {e}")
            enhanced_data["scrape_date_iso"] = None
    
    return enhanced_data

def enhance_post(post: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enhance a single post or reply with additional metadata fields.
    
    Args:
        post (Dict[str, Any]): A single post or reply dictionary
        
    Returns:
        Dict[str, Any]: The enhanced post with additional fields
    """
    # Create a copy to avoid modifying the original
    enhanced_post = post.copy()
    
    # Normalize date field
    if "date" in enhanced_post and enhanced_post["date"]:
        try:
            # Handle various date formats
            parsed_date = parse_date(enhanced_post["date"])
            if parsed_date:
                enhanced_post["date_iso"] = parsed_date.astimezone(timezone.utc).isoformat()
            else:
                enhanced_post["date_iso"] = None
        except Exception as e:
            logging.warning(f"Could not parse date '{enhanced_post.get('date')}': {e}")
            enhanced_post["date_iso"] = None
    else:
        enhanced_post["date_iso"] = None
    
    # Add media type flags
    enhanced_post["has_images"] = bool(enhanced_post.get("images", []))
    enhanced_post["has_video"] = bool(enhanced_post.get("videos", [])) 
    
    # Check for links in text
    text = enhanced_post.get("text", "")
    enhanced_post["has_links"] = bool(re.search(r'https?://\S+', text) or re.search(r'bit\.ly/\S+', text))
    
    # Generate image descriptions if images exist
    if enhanced_post["has_images"]:
        for img in enhanced_post.get("images", []):
            if img.get("description") is None:
                img["description"] = generate_image_description(img.get("url", ""))
    
    # Add engagement metadata placeholders
    enhanced_post.setdefault("engagement", {
        "likes": 0,
        "retweets": 0,
        "quotes": 0
    })
    
    return enhanced_post

def parse_date(date_str: str) -> Optional[datetime]:
    """
    Parse a date string into a datetime object with timezone.
    
    Handles common social media date formats including those with
    separators like "·" and various timezone indicators.
    
    Args:
        date_str (str): The date string to parse
        
    Returns:
        Optional[datetime]: A timezone-aware datetime object, or None if parsing fails
    """
    if not date_str or date_str.strip() == "":
        return None
    
    # Common X/Twitter date patterns
    if "·" in date_str:
        # Format like: "Apr 20, 2022 · 2:10 AM UTC"
        date_str = date_str.replace("·", "")
    
    try:
        # First try with dateutil parser
        parsed_date = parser.parse(date_str)
        
        # Ensure timezone is set
        if parsed_date.tzinfo is None:
            parsed_date = parsed_date.replace(tzinfo=timezone.utc)
            
        return parsed_date
    except:
        # Handle specific patterns manually if parsing fails
        patterns = [
            # Add any specific patterns here if needed
            (r'(\w{3} \d{1,2}, \d{4}) (\d{1,2}:\d{2} [AP]M) ([A-Z]{3,4})', 
             lambda m: parser.parse(f"{m.group(1)} {m.group(2)} {m.group(3)}"))
        ]
        
        for pattern, parser_func in patterns:
            match = re.search(pattern, date_str)
            if match:
                try:
                    return parser_func(match)
                except:
                    continue
                
    return None  # If all parsing attempts fail

def generate_image_description(image_url: str) -> str:
    """
    Generate a description for an image based on URL patterns.
    
    Uses URL and filename heuristics to make educated guesses about image content.
    In a production environment, this would be enhanced with OCR and image analysis.
    
    Args:
        image_url (str): URL of the image
        
    Returns:
        str: A description of the image based on URL analysis
    """
    # Simple URL-based heuristics
    url_lower = image_url.lower()
    
    # File name analysis
    filename = os.path.basename(urlparse(image_url).path)
    
    # Check for common patterns in the URL or filename
    if any(term in url_lower for term in ["map", "geography", "location"]):
        return "Map or geographic visualization"
    elif any(term in url_lower for term in ["chart", "graph", "plot", "figure"]):
        return "Data visualization or chart"
    elif any(term in url_lower for term in ["screenshot", "screen", "snap"]):
        return "Screenshot of application or website"
    elif "twitter" in url_lower or "tweet" in url_lower or "status" in url_lower:
        return "Screenshot of social media post"
    elif any(term in url_lower for term in ["profile", "avatar", "photo", "headshot"]):
        return "Profile picture or personal photo"
    elif any(ext in filename.lower() for ext in [".jpg", ".jpeg", ".png", ".gif"]):
        # Attempt to extract meaning from filename
        clean_name = re.sub(r'[0-9_\-.]', ' ', filename)
        if len(clean_name) > 5:  # If there's meaningful text in the filename
            return f"Image related to: {clean_name.strip()}"
    
    # Fallback for when we can't determine a specific type
    return "Attached image"