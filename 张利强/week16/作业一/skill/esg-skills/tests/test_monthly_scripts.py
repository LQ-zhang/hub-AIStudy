import contextlib
import importlib.util
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "esg-monthly-report" / "scripts"


class MonthlyScriptsTest(unittest.TestCase):
    def load(self, name):
        path = SCRIPTS / f"{name}.py"
        if not path.exists():
            self.fail(f"missing script: {path}")
        spec = importlib.util.spec_from_file_location(f"{name}_monthly_test", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def test_validate_report_flags_uncited_and_out_of_month_lines(self):
        mod = self.load("validate_report")
        text = (
            "# 标题\n"
            "- 没有来源\n"
            "- 2026-10-01 越界 [来源: https://example.com/a]\n"
            "- 正常 [来源: https://example.com/b]\n"
        )
        result = mod.validate_report_text(text, "2026-11")
        self.assertFalse(result["ok"])
        self.assertEqual([v["line"] for v in result["violations"]], [2, 3])

    def test_validate_report_accepts_cited_and_no_data_lines(self):
        mod = self.load("validate_report")
        text = (
            "# 标题\n"
            "- 2026-11-05 某政策发布 [来源: https://example.com/a]\n"
            "- 暂无数据\n"
        )
        result = mod.validate_report_text(text, "2026-11")
        self.assertTrue(result["ok"])
        self.assertEqual(result["violations"], [])

    def test_validate_report_ignores_blockquote_metadata(self):
        mod = self.load("validate_report")
        text = (
            "> 生成时间：2026-11-26\n"
            "- 2026-11-05 事实 [来源: https://example.com/a]\n"
        )
        result = mod.validate_report_text(text, "2026-11")
        self.assertTrue(result["ok"])

    def test_md_to_pdf_writes_nonempty_pdf(self):
        mod = self.load("md_to_pdf")
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "report.md"
            out = Path(tmp) / "report.pdf"
            src.write_text(
                "# 测试标题\n\n"
                "## 一、政策\n\n"
                "- 2026-11-05 中文内容测试 [来源: https://example.com/a]\n",
                encoding="utf-8",
            )
            mod.markdown_to_pdf(str(src), str(out), title="ESG 测试")
            self.assertTrue(out.exists())
            self.assertGreater(out.stat().st_size, 1000)

    def test_search_requires_api_key(self):
        mod = self.load("search_deepseek")
        stderr = io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=True), contextlib.redirect_stderr(stderr):
            code = mod.main(["--query", "test"])
        self.assertEqual(code, 2)
        self.assertIn("DEEPSEEK_API_KEY", stderr.getvalue())

    def test_search_normalizes_common_response_shapes(self):
        mod = self.load("search_deepseek")
        payload = {
            "data": [
                {
                    "name": "A",
                    "link": "https://example.com/a",
                    "content": "c",
                    "date": "2026-11-01",
                }
            ]
        }
        result = mod.normalize_results(payload, "q", None, None)
        self.assertEqual(
            result["results"][0],
            {
                "title": "A",
                "url": "https://example.com/a",
                "snippet": "c",
                "published_at": "2026-11-01",
            },
        )


if __name__ == "__main__":
    unittest.main()
