import pytest
import sys
import os

# Add the parent directory to the path so we can import from xread
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# pytest configuration and fixtures can be defined here

def pytest_configure(config):
    """
    Allows plugins and conftest files to perform initial configuration.
    This hook is called for every plugin and initial conftest file after command line options have been parsed.
    """
    pass

@pytest.fixture(scope="session")
def app_config():
    """
    Fixture for application configuration.
    Replace or extend this with actual configuration loading as needed.
    """
    return {"test": True}
