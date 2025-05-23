"""Unit tests for async file operations utility module in xread."""

import pytest
import json
from pathlib import Path
from xread.core.async_file import write_json_async, read_json_async, ensure_directory_async

@pytest.mark.asyncio
async def test_write_json_async(tmp_path: Path):
    """Test writing JSON data to a file asynchronously."""
    test_data = {"key": "value", "number": 42, "nested": {"a": 1}}
    test_file = tmp_path / "test.json"
    
    await write_json_async(test_file, test_data)
    
    with open(test_file, 'r', encoding='utf-8') as f:
        written_data = json.load(f)
    
    assert written_data == test_data

@pytest.mark.asyncio
async def test_read_json_async(tmp_path: Path):
    """Test reading JSON data from a file asynchronously."""
    test_data = {"key": "value", "number": 42, "nested": {"a": 1}}
    test_file = tmp_path / "test.json"
    
    with open(test_file, 'w', encoding='utf-8') as f:
        json.dump(test_data, f)
    
    read_data = await read_json_async(test_file)
    
    assert read_data == test_data

@pytest.mark.asyncio
async def test_ensure_directory_async(tmp_path: Path):
    """Test ensuring a directory exists asynchronously."""
    test_dir = tmp_path / "test_dir" / "nested"
    
    await ensure_directory_async(test_dir)
    
    assert test_dir.exists()
    assert test_dir.is_dir()
