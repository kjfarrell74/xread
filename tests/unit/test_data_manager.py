import pytest
from xread.data_manager import AsyncDataManager
from xread.settings import settings


@pytest.mark.asyncio
async def test_initialize_and_close(tmp_path):
    original_dir = settings.data_dir
    settings.data_dir = tmp_path
    manager = AsyncDataManager()
    await manager.initialize()
    assert manager.conn is not None
    await manager.close()
    settings.data_dir = original_dir
