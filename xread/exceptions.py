class XReadError(Exception):
    """Base class for exceptions in xread."""
    pass

class FetchError(XReadError):
    """Raised when fetching content from a URL fails."""
    pass

class ParseError(XReadError):
    """Raised when parsing HTML or other content fails."""
    pass

class AIModelError(XReadError):
    """Raised for errors related to AI model interactions."""
    # This might already exist in ai_models.py or be similar.
    # If it exists, ensure it inherits from XReadError or is compatible.
    # For now, define it here. If it's a duplicate, the worker can note it.
    pass

class BrowserError(XReadError):
    """Raised for errors related to browser automation (Playwright)."""
    pass
