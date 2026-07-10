import pytest

from headers import parse_header_line, parse_headers, redact_headers, render_headers


def test_hyphenated_header_names_are_accepted():
    header = parse_header_line("x-request-id: abc-123")
    assert header.name == "X-Request-Id"
    assert header.value == "abc-123"


def test_hash_inside_quoted_value_is_not_a_comment():
    headers = parse_headers(['etag: "abc#123"', "authorization: Bearer token # local note"])
    assert headers["Etag"] == "abc#123"
    assert headers["Authorization"] == "Bearer token"


def test_redaction_and_rendering_are_deterministic():
    headers = redact_headers({"Authorization": "secret", "X-Request-Id": "abc"})
    assert render_headers(headers) == ["Authorization: [redacted]", "X-Request-Id: abc"]


def test_malformed_line_is_rejected():
    with pytest.raises(ValueError):
        parse_header_line("no separator here")
