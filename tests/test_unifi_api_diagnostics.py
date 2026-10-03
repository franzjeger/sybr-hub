"""The API prober reports shape and never data.

Its whole reason to exist is that the vendor documentation cannot be read and
the response shape had to be guessed — badly, which is how get_isp_metrics came
to parse a path that was not there and render a grid of zeros. Reporting the
live shape removes the guessing. Reporting a live *value* would turn a
debugging aid into a customer-data leak, so that is the property under test.
"""

from __future__ import annotations

import json

from app.services.unifi_api import describe_shape


def test_nested_objects_are_reported_as_dotted_paths():
    shape = describe_shape({"data": {"wan": {"avgLatency": 12.5, "ispName": "Acme"}}})
    assert shape["data"] == "object"
    assert shape["data.wan"] == "object"
    assert shape["data.wan.avgLatency"] == "float"
    assert shape["data.wan.ispName"] == "string"


def test_an_array_records_its_length_and_describes_its_first_element():
    shape = describe_shape({"data": [{"siteId": "a"}, {"siteId": "b"}]})
    assert shape["data"] == "array[2]"
    assert shape["data[].siteId"] == "string"


def test_an_empty_array_is_distinguishable_from_a_populated_one():
    # "no readings" and "a reading full of nulls" produced identical zeros
    # before; telling them apart is the point of the exercise.
    assert describe_shape({"data": []})["data"] == "array[0]"
    assert describe_shape({"data": [{}]})["data"] == "array[1]"


def test_null_is_reported_as_null_rather_than_guessed():
    shape = describe_shape({"wan": {"uptime": None}})
    assert shape["wan.uptime"] == "null"


def test_no_value_ever_reaches_the_output():
    payload = {
        "data": [
            {
                "siteId": "SECRET-SITE-ID",
                "hostName": "customer-router.example.no",
                "apiKey": "SECRET-KEY-MATERIAL",
                "nested": {"ispName": "SECRET-ISP", "ips": ["10.9.9.9"]},
                "count": 12345,
                "enabled": True,
            }
        ]
    }
    serialised = json.dumps(describe_shape(payload))
    for secret in (
        "SECRET-SITE-ID",
        "customer-router.example.no",
        "SECRET-KEY-MATERIAL",
        "SECRET-ISP",
        "10.9.9.9",
        "12345",
    ):
        assert secret not in serialised, f"{secret!r} leaked into the shape report"
    # The keys themselves are schema and must survive, or the report is useless.
    assert "data[].nested.ispName" in serialised


def test_recursion_is_bounded():
    deep: dict = {}
    node = deep
    for _ in range(40):
        node["child"] = {}
        node = node["child"]
    shape = describe_shape(deep)
    assert len(shape) < 40

    wide = {f"key{i}": i for i in range(5000)}
    assert len(describe_shape(wide)) <= 400
