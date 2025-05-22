"""
Module for centralized data enhancement of scraped social media posts.

This module consolidates data transformation logic to enrich scraped social media data
with normalized dates, image descriptions, media flags, engagement metadata, and extracted
context or tags. It aims to eliminate redundancy across different processing stages and
ensure consistent data enhancement throughout the pipeline.
"""

import re
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse
import os
from dateutil import parser

# Setup logging
logging.basicConfig(level=logging.INFO)

def enhance_post_json(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enhance a scraped social media post JSON with additional metadata.
    
    This function processes a raw scraped social media post JSON, enriching it with:
    - Normalized date fields (ISO 8601 timestamps in UTC)
    - Image descriptions using heuristics and filename analysis
    - Media type flags (has_images, has_video, has_links)
    - Engagement metadata placeholders
    - Top-level research placeholders
    
    Args:
        data (Dict[str, Any]): The original scraped post JSON containing main_post, replies, etc.
        
    Returns:
        Dict[str, Any]: Enhanced post JSON with all original data preserved plus additional fields
    """
    # Create a deep copy to avoid modifying the original
    enhanced_data = data.copy()
    
    # Process main post
    if "main_post" in enhanced_data:
        enhanced_data["main_post"] = enhance_single_post(enhanced_data["main_post"])
    
    # Process replies
    if "replies" in enhanced_data:
        enhanced_data["replies"] = [enhance_single_post(reply) for reply in enhanced_data["replies"]]
        # Infer missing reply dates based on main post date if available
        main_post_date = enhanced_data["main_post"].get("date", "")
        enhanced_data["replies"] = infer_reply_dates(main_post_date, enhanced_data["replies"])
    
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

def enhance_single_post(post: Dict[str, Any]) -> Dict[str, Any]:
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
    text = enhanced_post.get("text", "")
    enhanced_post["has_links"] = bool(re.search(r'https?://\S+', text) or re.search(r'bit\.ly/\S+', text))
    
    # Generate image descriptions if images exist
    if enhanced_post["has_images"]:
        for img in enhanced_post.get("images", []):
            if img.get("description") is None or not img.get("description"):
                img["description"] = generate_image_description(img.get("url", ""))
    
    # Add engagement metadata placeholders
    for metric in ['likes', 'retweets', 'replies_count', 'quotes']:
        if metric not in enhanced_post or enhanced_post.get(metric) in [0, '0', None]:
            enhanced_post[metric] = None
    
    return enhanced_post

def infer_reply_dates(main_post_date_str: str, replies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    If replies have missing dates, estimate them based on main post date + reply order.
    
    Args:
        main_post_date_str (str): The date string of the main post
        replies (List[Dict[str, Any]]): List of reply dictionaries
        
    Returns:
        List[Dict[str, Any]]: Updated list of replies with inferred dates if missing
    """
    try:
        main_date = datetime.fromisoformat(main_post_date_str.replace('Z', '+00:00'))
    except Exception:
        main_date = datetime.utcnow()

    for i, reply in enumerate(replies):
        if 'date' not in reply or not reply['date']:
            # Estimate date by adding i+1 minutes to main post date
            estimated_date = main_date + timedelta(minutes=i + 1)
            reply['date'] = estimated_date.isoformat()
        # Fix engagement metrics: set to None if zero or missing
        for metric in ['likes', 'retweets', 'replies_count']:
            if metric not in reply or reply.get(metric) in [0, '0', None]:
                reply[metric] = None
    return replies

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
    return None

def generate_image_description(image_url: str) -> str:
    """
    Generate a description for an image based on URL patterns.
    
    Uses URL and filename heuristics to make educated guesses about image content.
    
    Args:
        image_url (str): URL of the image
        
    Returns:
        str: A description of the image based on URL analysis
    """
    url_lower = image_url.lower()
    filename = os.path.basename(urlparse(image_url).path)
    
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
        clean_name = re.sub(r'[0-9_\-.]', ' ', filename)
        if len(clean_name) > 5:
            return f"Image related to: {clean_name.strip()}"
    return "Attached image"

def normalize_images(images: List[Any], additional_context: str = "") -> List[Any]:
    """
    Add descriptions to images if missing, using provided context or heuristics.
    
    Args:
        images (List[Any]): List of image objects or dictionaries
        additional_context (str): Additional text context (e.g., from a report) to extract descriptions
        
    Returns:
        List[Any]: Updated list of images with descriptions
    """
    descriptions = []
    if additional_context:
        match = re.search(r'Image descriptions?:\s*(.*?)(?:\n\n|$)', additional_context, re.DOTALL | re.IGNORECASE)
        if match:
            desc_text = match.group(1)
            descriptions = [line.strip() for line in desc_text.split('\n') if line.strip()]

    for i, img in enumerate(images):
        description = None
        if isinstance(img, dict):
            description = img.get('description')
        else:
            description = getattr(img, 'description', None)

        if not description:
            if i < len(descriptions):
                new_desc = descriptions[i]
            else:
                new_desc = generate_image_description(img.get('url', '') if isinstance(img, dict) else getattr(img, 'url', ''))
            if isinstance(img, dict):
                img['description'] = new_desc
            else:
                setattr(img, 'description', new_desc)
        elif description == "No description available" and i < len(descriptions):
            if isinstance(img, dict):
                img['description'] = descriptions[i]
            else:
                setattr(img, 'description', descriptions[i])
    return images

# Function to extract factual context from AI-generated reports
def extract_factual_context(text_content: str) -> List[str]:
    """
    Extract factual context from provided text content, specifically looking for a 'Factual Context' section.
    
    Args:
        text_content (str): Text content to analyze
        
    Returns:
        List[str]: List of factual statements or context points
    """
    factual_context = []
    # Search for 'Factual Context' section (case-insensitive)
    match = re.search(r'(?:##\s*|#*\s*)Factual Context\s*[:\n-]*(.*?)(?:\n##|\n#*|$)', text_content, re.DOTALL | re.IGNORECASE)
    if match:
        content = match.group(1).strip()
        # Extract bullet points
        lines = [line.strip() for line in content.split('\n') if line.strip().startswith(('-', '*', '•'))]
        if lines:
            factual_context.extend(lines)
        else:
            # If no bullets found, take all non-empty lines
            lines = [line.strip() for line in content.split('\n') if line.strip()]
            factual_context.extend(lines)
    else:
        # Fallback heuristic for content without a specific section
        sentences = re.split(r'(?<=[.!?]) +', text_content)
        for sentence in sentences:
            if any(keyword in sentence.lower() for keyword in ['fact', 'confirmed', 'reported', 'according']):
                factual_context.append(sentence.strip())
    return factual_context if factual_context else ["No factual context extracted."]

def extract_topic_tags(main_text: str, additional_text: str = "") -> List[str]:
    """
    Extract or generate topic tags from main text and additional content.
    Currently a placeholder for future NLP integration.
    
    Args:
        main_text (str): Main post text
        additional_text (str): Additional text content (e.g., from a report)
        
    Returns:
        List[str]: List of topic tags
    """
    tags = set()
    words = re.findall(r'\b[A-Z][a-zA-Z0-9]+\b', main_text)
    tags.update(words)

    if additional_text:
        match = re.search(r'##\s*Topics\s*:(.*?)(?:\n##|$)', additional_text, re.DOTALL | re.IGNORECASE)
        if match:
            topics_text = match.group(1)
            topics = re.split(r'[,\n]+', topics_text)
            for topic in topics:
                topic = topic.strip()
                if topic:
                    tags.add(topic)

    if not tags:
        fallback_tags = ['gas prices', 'Trump', 'MAGA', 'energy policy', 'economic narrative']
        tags.update(fallback_tags)

    return list(tags)[:10]
