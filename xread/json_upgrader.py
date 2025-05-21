import json
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional


def load_json_file(filepath: str) -> Dict[str, Any]:
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json_file(data: Dict[str, Any], filepath: str) -> None:
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def infer_reply_dates(main_post_date_str: str, replies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """If replies have missing dates, estimate them based on main post date + reply order."""
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


def extract_factual_context(perplexity_report: str) -> List[str]:
    """Extract factual context from the perplexity report using regex or simple parsing."""
    factual_context = []
    # Look for a section starting with "## Factual Context:" or similar
    match = re.search(r'##\s*Factual Context\s*:(.*?)(?:\n##|$)', perplexity_report, re.DOTALL | re.IGNORECASE)
    if match:
        content = match.group(1).strip()
        # Split into lines or sentences as key facts
        lines = [line.strip() for line in content.split('\n') if line.strip()]
        factual_context.extend(lines)
    else:
        # Fallback: try to extract key sentences mentioning facts
        sentences = re.split(r'(?<=[.!?]) +', perplexity_report)
        for sentence in sentences:
            if any(keyword in sentence.lower() for keyword in ['fact', 'confirmed', 'reported', 'according']):
                factual_context.append(sentence.strip())
    return factual_context


def extract_topic_tags(main_post_text: str, perplexity_report: str) -> List[str]:
    """Extract or generate topic tags from main post text and perplexity report."""
    # Simple heuristic: extract capitalized words or known keywords
    tags = set()

    # Extract capitalized words from main post text
    words = re.findall(r'\b[A-Z][a-zA-Z0-9]+\b', main_post_text)
    tags.update(words)

    # Extract tags from perplexity report if it contains a "Topics" section
    match = re.search(r'##\s*Topics\s*:(.*?)(?:\n##|$)', perplexity_report, re.DOTALL | re.IGNORECASE)
    if match:
        topics_text = match.group(1)
        # Split by commas or newlines
        topics = re.split(r'[,\n]+', topics_text)
        for topic in topics:
            topic = topic.strip()
            if topic:
                tags.add(topic)

    # Add some fallback tags if empty
    if not tags:
        fallback_tags = ['gas prices', 'Trump', 'MAGA', 'energy policy', 'economic narrative']
        tags.update(fallback_tags)

    # Return as list, limit to top 10 tags
    return list(tags)[:10]


def normalize_images(images: List[Any], perplexity_report: str) -> List[Any]:
    """Add description to images if missing, using fallback from perplexity report."""
    # Try to extract image descriptions from perplexity report (simple heuristic)
    descriptions = []
    match = re.search(r'Image descriptions?:\s*(.*?)(?:\n\n|$)', perplexity_report, re.DOTALL | re.IGNORECASE)
    if match:
        desc_text = match.group(1)
        descriptions = [line.strip() for line in desc_text.split('\n') if line.strip()]

    for i, img in enumerate(images):
        # img may be an object with attributes or a dict
        description = None
        if isinstance(img, dict):
            description = img.get('description')
        else:
            description = getattr(img, 'description', None)

        if not description:
            if i < len(descriptions):
                if isinstance(img, dict):
                    img['description'] = descriptions[i]
                else:
                    setattr(img, 'description', descriptions[i])
            else:
                if isinstance(img, dict):
                    img['description'] = "No description available"
                else:
                    setattr(img, 'description', "No description available")
    return images


def build_scrape_meta(scrape_date: str, source: str) -> Dict[str, Any]:
    if not source:
        source = "x.com"
    return {
        "scraped_at": scrape_date,
        "source": source,
        "scraper": "perplexity-to-json-v1"
    }


def upgrade_perplexity_json(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """Transform raw Perplexity-style JSON into the perfect structured format."""

    main_post = raw_data.get('main_post', {})
    replies = raw_data.get('replies', [])
    perplexity_report = raw_data.get('perplexity_report', '')
    scrape_date = raw_data.get('scrape_date', datetime.utcnow().isoformat())
    source = raw_data.get('source', None)

    # Step 1: Infer missing reply dates and fix engagement metrics in replies
    replies = infer_reply_dates(main_post.get('date', ''), replies)

    # Step 2: Extract factual context
    factual_context = extract_factual_context(perplexity_report)
    if not factual_context:
        factual_context = ["No factual context extracted."]

    # Step 3: Extract topic tags
    topic_tags = raw_data.get('topic_tags', [])
    if not topic_tags:
        topic_tags = extract_topic_tags(main_post.get('text', ''), perplexity_report)

    # Step 4: Normalize images and add descriptions from perplexity report
    images = main_post.get('images', [])
    images = normalize_images(images, perplexity_report)
    main_post['images'] = images

    # Step 5: Build scrape meta with default source if missing
    scrape_meta = build_scrape_meta(scrape_date, source)

    # Step 6: Build final structured JSON
    upgraded = {
        "main_post": main_post,
        "replies": replies,
        "factual_context": factual_context,
        "topic_tags": topic_tags,
        "scrape_meta": scrape_meta
    }

    return upgraded


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python3 json_upgrader.py <input_json> <output_json>")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    raw_json = load_json_file(input_path)
    upgraded_json = upgrade_perplexity_json(raw_json)
    save_json_file(upgraded_json, output_path)
    print(f"Upgraded JSON saved to {output_path}")
