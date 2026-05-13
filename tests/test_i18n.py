"""Tests for app.reports.i18n — translations and the T helper class."""

from __future__ import annotations

from app.reports.i18n import TRANSLATIONS, T, get_translations


class TestGetTranslations:
    def test_norwegian_strings(self):
        strings = get_translations("no")
        assert strings["report_title_customer"] == "IT-Sikkerhetsrapport"
        assert strings["confidential"] == "Konfidensiell"

    def test_english_strings(self):
        strings = get_translations("en")
        assert strings["report_title_customer"] == "IT Security Report"
        assert strings["confidential"] == "Confidential"

    def test_unknown_lang_falls_back_to_norwegian(self):
        strings = get_translations("fr")
        assert strings["report_title_customer"] == "IT-Sikkerhetsrapport"


class TestTClass:
    def test_attribute_access_norwegian(self):
        t = T("no")
        assert t.summary == "Sammendrag"

    def test_attribute_access_english(self):
        t = T("en")
        assert t.summary == "Summary"

    def test_missing_key_returns_key_name(self):
        t = T("no")
        assert t.nonexistent_key_xyz == "nonexistent_key_xyz"

    def test_call_with_format_params(self):
        t = T("en")
        result = t("mfa_missing_title", count=5)
        assert result == "5 user(s) missing multi-factor authentication"

    def test_call_norwegian_with_format_params(self):
        t = T("no")
        result = t("mfa_missing_title", count=3)
        assert result == "3 bruker(e) mangler tofaktorautentisering"

    def test_call_without_params(self):
        t = T("en")
        assert t("summary") == "Summary"


class TestTranslationCompleteness:
    def test_all_keys_have_both_languages(self):
        """Every key in TRANSLATIONS must have both 'no' and 'en' entries."""
        missing = []
        for key, langs in TRANSLATIONS.items():
            if "no" not in langs:
                missing.append(f"{key}: missing 'no'")
            if "en" not in langs:
                missing.append(f"{key}: missing 'en'")
        assert missing == [], f"Incomplete translations:\n" + "\n".join(missing)

    def test_translations_are_non_empty_strings(self):
        """No translation value should be empty."""
        empty = []
        for key, langs in TRANSLATIONS.items():
            for lang, value in langs.items():
                if not isinstance(value, str) or not value.strip():
                    empty.append(f"{key}[{lang}]")
        assert empty == [], f"Empty translations: {empty}"
