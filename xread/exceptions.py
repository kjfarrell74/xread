"""Custom exception classes for the xread application."""

class XReadError(Exception):
    """Base class for exceptions in this application."""
    pass

class DatabaseError(XReadError):
    """Raised for database-related errors."""
    pass

class ScrapingError(XReadError):
    """Raised for errors during web scraping."""
    pass

class AIModelError(XReadError):
    """Raised for errors related to AI model interactions."""
    pass

class ConfigurationError(XReadError):
    """Raised for application configuration errors."""
    pass

class FileOperationError(XReadError):
    """Raised for file input/output errors."""
    pass
