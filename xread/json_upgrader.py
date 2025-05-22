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


from xread.data_enhancer import infer_reply_dates


from xread.data_enhancer import extract_factual_context


from xread.data_enhancer import extract_topic_tags


from xread.data_enhancer import normalize_images


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
