"""Custom exceptions for XReader application."""


class XReaderError(Exception):
    """Base exception for all XReader errors."""
    pass


class ScrapingError(XReaderError):
    """Raised when scraping operations fail."""
    pass


class NetworkError(ScrapingError):
    """Raised when network operations fail during scraping."""
    pass


class ParseError(ScrapingError):
    """Raised when HTML parsing fails."""
    pass


class ValidationError(XReaderError):
    """Raised when data validation fails."""
    pass


class InvalidURLError(ValidationError):
    """Raised when URL format is invalid."""
    pass


class InvalidStatusIDError(ValidationError):
    """Raised when status ID is invalid."""
    pass


class DatabaseError(XReaderError):
    """Raised when database operations fail."""
    pass


class AIModelError(XReaderError):
    """Raised when AI model operations fail."""
    pass


class APIError(AIModelError):
    """Raised when external API calls fail."""
    pass


class RateLimitError(APIError):
    """Raised when API rate limits are exceeded."""
    pass


class PluginError(XReaderError):
    """Raised when plugin operations fail."""
    pass


class ConfigurationError(XReaderError):
    """Raised when configuration is invalid or missing."""
    pass


class SecurityError(XReaderError):
    """Raised when security validation fails."""
    pass