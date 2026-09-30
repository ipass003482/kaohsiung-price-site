import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from scripts import fetch_retail_prices as retail


OLD = "2026-09-29T14:00+08:00"
NEW = "2026-09-30T10:00+08:00"
LATER = "2026-10-01T10:00+08:00"


def source(key="pxmart", date=OLD, price=31):
    return {
        "id": key,
        "name": key,
        "status": "ok",
        "collected_at": date,
        "errors": [],
        "product_count": 1,
        "products": [{"source": key, "canonical": "小白菜", "name": "小白菜 250g", "price": price}],
    }


def blocked():
    return {"id": "pxmart", "name": "全聯小時達", "status": "error", "error_http_status": 403,
            "errors": ["HTTP Error 403: Forbidden"], "product_count": 0, "products": []}


class RetailRefreshTests(unittest.TestCase):
    def test_repeated_failure_keeps_prices_and_their_original_date(self):
        old = source()
        old.pop("collected_at")  # Existing schema v1 snapshot.
        history = retail.previous_sources([{"collected_at": OLD, "sources": {"pxmart": old}}])
        first = retail.preserve_prices(blocked(), history["pxmart"], NEW)
        history = retail.previous_sources([{"collected_at": NEW, "sources": {"pxmart": first}}])
        second = retail.preserve_prices(blocked(), history["pxmart"], LATER)
        self.assertEqual(second["products"], old["products"])
        self.assertEqual(second["collected_at"], OLD)
        self.assertEqual(second["last_attempt_at"], LATER)
        self.assertEqual(second["status"], "stale")
        self.assertEqual(second["error_http_status"], 403)

    def test_newest_price_date_wins_per_source_over_newest_failed_attempt(self):
        seed = {"collected_at": NEW, "sources": {"pxmart": source(date=NEW, price=32), "carrefour": source("carrefour")}}
        cache = {"collected_at": LATER, "sources": {
            "pxmart": retail.preserve_prices(blocked(), source(), LATER),
            "carrefour": source("carrefour", NEW, 35),
        }}
        chosen = retail.previous_sources([seed, cache])
        self.assertEqual(chosen["pxmart"]["products"][0]["price"], 32)
        self.assertEqual(chosen["carrefour"]["products"][0]["price"], 35)
        self.assertEqual(chosen["pxmart"]["collected_at"], NEW)

    def test_success_replaces_stale_data_and_clears_cached_flag(self):
        stale = retail.preserve_prices(blocked(), source(), NEW)
        recovered = retail.preserve_prices(source(price=33), stale, LATER)
        self.assertEqual(recovered["products"][0]["price"], 33)
        self.assertEqual(recovered["status"], "ok")
        self.assertEqual(recovered["collected_at"], LATER)
        self.assertFalse(recovered["using_cached_data"])
        self.assertEqual(recovered["errors"], [])

    def test_missing_or_undated_history_does_not_invent_prices(self):
        invalid = {"collected_at": NEW, "sources": {"pxmart": {**source(), "status": "stale", "collected_at": None}}}
        self.assertEqual(retail.previous_sources([invalid]), {})
        result = retail.preserve_prices(blocked(), None, NEW)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["products"], [])
        self.assertIsNone(result["collected_at"])

    def test_access_denial_and_rate_limit_stop_after_one_request(self):
        for collect in (retail.collect_pxmart, retail.collect_carrefour):
            for code in (401, 403, 429):
                with self.subTest(source=collect.__name__, code=code):
                    error = HTTPError("https://example.test/", code, "Denied", {}, None)
                    with patch.object(retail, "urlopen", side_effect=error) as request, patch.object(retail.time, "sleep"):
                        result = collect()
                    self.assertEqual(request.call_count, 1)
                    self.assertEqual(result["error_http_status"], code)
                    self.assertEqual(result["product_count"], 0)

    def test_temporary_server_error_gets_one_retry(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.headers.get_content_charset.return_value = "utf-8"
        response.read.return_value = b"<html>recovered</html>"
        error = HTTPError("https://example.test/", 503, "Unavailable", {}, None)
        with patch.object(retail, "urlopen", side_effect=[error, response]) as request, patch.object(retail.time, "sleep"):
            result = retail.fetch_html("https://example.test/")
        self.assertIn("recovered", result)
        self.assertEqual(request.call_count, 2)

    def test_persistent_timeouts_have_a_finite_request_budget(self):
        with patch.object(retail, "urlopen", side_effect=TimeoutError("timed out")) as request, patch.object(retail.time, "sleep"):
            result = retail.collect_pxmart()
        self.assertEqual(request.call_count, 6)  # Three searches, at most two attempts each.
        self.assertEqual(len(result["errors"]), 3)

    def test_changed_page_structure_is_not_treated_as_success(self):
        with patch.object(retail, "PX_QUERIES", ["菜"]), patch.object(retail, "fetch_html", return_value="<html>Changed layout</html>"), patch.object(retail.time, "sleep"):
            result = retail.collect_pxmart()
        self.assertEqual(result["status"], "error")
        self.assertTrue(result["errors"])
        self.assertEqual(retail.preserve_prices(result, source(), NEW)["status"], "stale")

    def test_written_snapshot_contains_cached_and_fresh_prices_consistently(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "retail.json"
            target.write_text(json.dumps({"collected_at": OLD, "sources": {"pxmart": source()}}), encoding="utf-8")
            with patch("sys.argv", ["collector", "--output", str(target)]), patch.object(retail, "collect_pxmart", return_value=blocked()), patch.object(retail, "collect_carrefour", return_value=source("carrefour", NEW, 35)), patch.object(retail, "now_taipei", return_value=NEW), patch.object(retail, "report_sources"):
                retail.main()
            result = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(result["sources"]["pxmart"]["collected_at"], OLD)
            self.assertEqual(result["sources"]["carrefour"]["collected_at"], NEW)
            self.assertEqual(result["products"], result["sources"]["pxmart"]["products"] + result["sources"]["carrefour"]["products"])
            self.assertFalse(target.with_suffix(".json.tmp").exists())


if __name__ == "__main__":
    unittest.main()
