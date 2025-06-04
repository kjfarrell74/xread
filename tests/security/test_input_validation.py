import pytest
from xread.security_patches import SecurityValidator


def test_validate_status_id():
    assert SecurityValidator.validate_status_id("123456789012345")
    assert not SecurityValidator.validate_status_id("abc")


def test_validate_url():
    assert SecurityValidator.validate_url("https://twitter.com/test/status/1")
    assert not SecurityValidator.validate_url("https://malicious.com")
