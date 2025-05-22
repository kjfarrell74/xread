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

from xread.data_enhancer import enhance_post_json

from xread.data_enhancer import enhance_single_post

from xread.data_enhancer import parse_date

from xread.data_enhancer import generate_image_description
