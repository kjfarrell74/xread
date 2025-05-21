import unittest
import asyncio
from pathlib import Path
from unittest.mock import patch

# Adjust import path if necessary, assuming xread is importable
from xread.data_manager import DataManager
from xread.settings import Settings # To override settings for testing

class TestDataManager(unittest.TestCase):

    def setUp(self):
        # Override settings to use an in-memory database and a temporary data directory
        self.test_data_dir = Path("test_xread_data_temp")
        self.test_db_path = self.test_data_dir / "xread_data_test.db"
        
        # Ensure the temp data dir is clean before each test if it's created by DataManager
        # For in-memory, this is less of an issue for the DB itself.
        # DataManager also writes JSON files, so a temp dir for those is good.
        
        self.settings_override = {
            "data_dir": self.test_data_dir,
            # The DataManager constructs db_path from data_dir.
            # To force in-memory for DB and still have a data_dir for JSON:
            # We can patch DataManager._connect_db to use :memory:
            # Or, for simplicity in this initial test, let it write a test DB file
            # that we can clean up. Let's go with a file-based test DB first.
        }
        
        # It's important that DataManager uses a different DB for tests.
        # We can achieve this by patching settings.data_dir *before* DataManager is instantiated.
        # Pydantic settings are usually loaded once.
        # A cleaner way is to make DataManager accept db_path or settings instance.
        # For now, let's assume DataManager will use a DB inside the overridden data_dir.

        # Create the DataManager instance for the test
        # Patching settings directly can be tricky if already imported.
        # We will patch the settings object that the DataManager instance would use.
        # This is an initial setup, might need refinement based on how settings are structured.

    def tearDown(self):
        # Clean up the test database file and temp directory
        if self.test_db_path.exists():
            self.test_db_path.unlink()
        if self.test_data_dir.exists():
            # Remove JSON files etc.
            for item in self.test_data_dir.iterdir():
                if item.is_file():
                    item.unlink()
                elif item.is_dir(): # e.g. scraped_data subdirectory
                    for sub_item in item.iterdir():
                        sub_item.unlink()
                    item.rmdir()
            self.test_data_dir.rmdir()

    @patch('xread.data_manager.settings') # Patch where settings is imported in data_manager.py
    def test_initialize_and_count(self, mock_settings):
        # Configure the mock settings object
        mock_settings.data_dir = self.test_data_dir
        # Any other settings DataManager might need from the global 'settings' object
        
        # DataManager will now use self.test_data_dir due to the patch
        dm = DataManager()
        
        # Run async initialize
        asyncio.run(dm.initialize())
        
        self.assertIsNotNone(dm.conn, "Database connection should be established.")
        
        # Check initial count
        count = dm.count()
        self.assertEqual(count, 0, "Initial post count should be 0.")
        
        # Test DB file creation (optional, depends on final DB strategy for tests)
        # For this initial test, if using a file DB, it should be created.
        # If we switch to fully in-memory by patching _connect_db, this assertion changes.
        # self.assertTrue((self.test_data_dir / 'xread_data.db').exists())


if __name__ == '__main__':
    unittest.main()
