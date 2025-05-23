"""Async file operations utility module for xread."""

import aiofiles
import aiofiles.os
from pathlib import Path
from typing import Union, Dict, Any
import json

async def write_json_async(file_path: Path, data: Dict[str, Any]) -> None:
    """Write JSON data to a file asynchronously.
    
    Args:
        file_path (Path): The path to the file to write to.
        data (Dict[str, Any]): The data to write as JSON.
    """
    async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
        await f.write(json.dumps(data, indent=2, ensure_ascii=False))

async def read_json_async(file_path: Path) -> Dict[str, Any]:
    """Read JSON data from a file asynchronously.
    
    Args:
        file_path (Path): The path to the file to read from.
        
    Returns:
        Dict[str, Any]: The data read from the JSON file.
    """
    async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
        content = await f.read()
        return json.loads(content)

async def ensure_directory_async(directory: Path) -> None:
    """Ensure a directory exists, creating it if necessary, asynchronously.
    
    Args:
        directory (Path): The directory path to ensure exists.
    """
    await aiofiles.os.makedirs(directory, exist_ok=True)
