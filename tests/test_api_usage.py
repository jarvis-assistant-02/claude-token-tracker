"""Tests for API usage header parsing."""
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from tracker.api_usage import fetch_real_usage


def _mock_response(headers: dict, status_code: int = 200):
    r = MagicMock()
    r.status_code = status_code
    r.headers = headers
    return r


VALID_HEADERS = {
    "anthropic-ratelimit-unified-7d-utilization": "0.19",
    "anthropic-ratelimit-unified-7d-reset": "1782720000",
    "anthropic-ratelimit-unified-7d-status": "allowed",
    "anthropic-ratelimit-unified-5h-utilization": "0.05",
    "anthropic-ratelimit-unified-5h-reset": "1782276600",
}


@patch("tracker.api_usage.platform.system", return_value="Darwin")
@patch("tracker.api_usage._get_oauth_token", return_value="sk-ant-oat01-test")
@patch("tracker.api_usage.requests.post")
def test_fetch_real_usage_parses_headers(mock_post, _mock_token, _mock_platform):
    mock_post.return_value = _mock_response(VALID_HEADERS)
    result = fetch_real_usage()

    assert result is not None
    assert result["utilization_7d"] == pytest.approx(0.19)
    assert result["status_7d"] == "allowed"
    assert result["utilization_5h"] == pytest.approx(0.05)


@patch("tracker.api_usage.platform.system", return_value="Darwin")
@patch("tracker.api_usage._get_oauth_token", return_value="sk-ant-oat01-test")
@patch("tracker.api_usage.requests.post")
def test_fetch_real_usage_parses_reset_timestamp(mock_post, _mock_token, _mock_platform):
    mock_post.return_value = _mock_response(VALID_HEADERS)
    result = fetch_real_usage()

    assert isinstance(result["reset_7d"], datetime)
    assert result["reset_7d"].tzinfo == timezone.utc
    assert result["reset_7d"].timestamp() == 1782720000


@patch("tracker.api_usage.platform.system", return_value="Darwin")
@patch("tracker.api_usage._get_oauth_token", return_value="sk-ant-oat01-test")
@patch("tracker.api_usage.requests.post")
def test_fetch_real_usage_returns_none_when_headers_missing(mock_post, _mock_token, _mock_platform):
    mock_post.return_value = _mock_response({})   # no rate-limit headers
    result = fetch_real_usage()
    assert result is None


@patch("tracker.api_usage.platform.system", return_value="Darwin")
@patch("tracker.api_usage._get_oauth_token", return_value=None)
def test_fetch_real_usage_returns_none_without_token(_mock_token, _mock_platform):
    result = fetch_real_usage()
    assert result is None


@patch("tracker.api_usage.platform.system", return_value="Linux")
def test_fetch_real_usage_returns_none_on_non_macos(_mock_platform):
    result = fetch_real_usage()
    assert result is None


@patch("tracker.api_usage.platform.system", return_value="Darwin")
@patch("tracker.api_usage._get_oauth_token", return_value="sk-ant-oat01-test")
@patch("tracker.api_usage.requests.post", side_effect=Exception("timeout"))
def test_fetch_real_usage_returns_none_on_network_error(mock_post, _mock_token, _mock_platform):
    result = fetch_real_usage()
    assert result is None
