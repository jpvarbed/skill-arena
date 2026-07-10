import pytest

from paginator import flatten_pages, paginate_records, summarize_pages


def records(count):
    return [{"id": f"r{index}", "value": index} for index in range(count)]


def test_page_ranges_are_half_open_and_cover_all_records():
    pages = paginate_records(records(7), 3)
    assert [(page.start, page.end, len(page.items)) for page in pages] == [(0, 3, 3), (3, 6, 3), (6, 7, 1)]
    assert [item["id"] for item in flatten_pages(pages)] == [f"r{index}" for index in range(7)]


def test_empty_input_has_no_pages():
    assert paginate_records([], 5) == []
    assert summarize_pages([]) == {"pages": 0, "records": 0, "first_id": None, "last_id": None}


def test_invalid_page_size_is_rejected():
    with pytest.raises(ValueError):
        paginate_records(records(2), 0)


def test_missing_id_is_reported():
    with pytest.raises(ValueError):
        paginate_records([{"id": "ok"}, {"value": 3}], 2)
