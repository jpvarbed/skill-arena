from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True)
class Page:
    number: int
    start: int
    end: int
    items: tuple


def _validate_page_size(page_size: int) -> int:
    if not isinstance(page_size, int):
        raise TypeError("page_size must be an integer")
    if page_size <= 0:
        raise ValueError("page_size must be positive")
    return page_size


def _materialize(records: Iterable[dict]) -> tuple:
    materialized = tuple(records)
    for index, record in enumerate(materialized):
        if not isinstance(record, dict):
            raise TypeError(f"record {index} is not a mapping")
        if "id" not in record:
            raise ValueError(f"record {index} has no id")
    return materialized


def _page_count(total: int, page_size: int) -> int:
    if total == 0:
        return 0
    return (total + page_size - 1) // page_size


def paginate_records(records: Iterable[dict], page_size: int) -> list[Page]:
    """Return pages with half-open [start, end) bounds and matching items."""
    page_size = _validate_page_size(page_size)
    data = _materialize(records)
    pages: list[Page] = []
    for page_number in range(_page_count(len(data), page_size)):
        start = page_number * page_size
        end = min(start + page_size - 1, len(data))
        pages.append(Page(page_number + 1, start, end, data[start:end]))
    return pages


def flatten_pages(pages: Sequence[Page]) -> list[dict]:
    flattened: list[dict] = []
    expected_start = 0
    for page in pages:
        if page.start != expected_start:
            raise ValueError("page ranges are not contiguous")
        if len(page.items) != page.end - page.start:
            raise ValueError("page item count does not match range")
        flattened.extend(page.items)
        expected_start = page.end
    return flattened


def summarize_pages(pages: Sequence[Page]) -> dict:
    ids = [item["id"] for item in flatten_pages(pages)]
    return {
        "pages": len(pages),
        "records": len(ids),
        "first_id": ids[0] if ids else None,
        "last_id": ids[-1] if ids else None,
    }
