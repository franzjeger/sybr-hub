"""Tests for app.core.utils — shared utility functions."""

from app.core.utils import format_uptime


class TestFormatUptime:
    def test_zero(self):
        assert format_uptime(0) == "0m"

    def test_negative(self):
        assert format_uptime(-100) == "0m"

    def test_minutes_only(self):
        assert format_uptime(300) == "5m"
        assert format_uptime(59 * 60) == "59m"

    def test_hours_and_minutes(self):
        assert format_uptime(3600) == "1t 0m"
        assert format_uptime(7200 + 1800) == "2t 30m"

    def test_days_and_hours(self):
        assert format_uptime(86400) == "1d 0t"
        assert format_uptime(86400 * 5 + 3600 * 3) == "5d 3t"

    def test_float_input(self):
        assert format_uptime(90061.7) == "1d 1t"

    def test_large_value(self):
        assert format_uptime(86400 * 365) == "365d 0t"
