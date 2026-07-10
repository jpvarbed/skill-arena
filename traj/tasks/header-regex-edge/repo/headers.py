import re
from dataclasses import dataclass
from typing import Iterable


HEADER_RE = re.compile(r"^([A-Za-z0-9_]+):\s*(.*?)\s*(?:#.*)?$")


@dataclass(frozen=True)
class Header:
    name: str
    value: str


def _normalize_name(name: str) -> str:
    return "-".join(part.capitalize() for part in name.replace("_", "-").split("-"))


def parse_header_line(line: str) -> Header | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    match = HEADER_RE.match(stripped)
    if not match:
        raise ValueError(f"invalid header line: {line}")
    name, value = match.groups()
    value = _unquote(value.strip())
    if not value:
        raise ValueError(f"missing value for {name}")
    return Header(_normalize_name(name), value)


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1]
    return value


def parse_headers(lines: Iterable[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in lines:
        header = parse_header_line(line)
        if header is None:
            continue
        parsed[header.name] = header.value
    return parsed


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    redacted = {}
    for name, value in headers.items():
        if name.lower() in {"authorization", "x-api-key"}:
            redacted[name] = "[redacted]"
        else:
            redacted[name] = value
    return redacted


def render_headers(headers: dict[str, str]) -> list[str]:
    return [f"{name}: {value}" for name, value in sorted(headers.items())]
