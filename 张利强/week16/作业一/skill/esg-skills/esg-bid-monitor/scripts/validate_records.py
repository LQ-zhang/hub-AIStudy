"""校验 ESG 招投标记录是否符合统一 Schema。"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

REQUIRED_FIELDS = (
    "project_name",
    "buyer",
    "winner",
    "amount_wan",
    "publish_date",
    "category",
    "source_url",
)
NON_EMPTY_FIELDS = ("project_name", "buyer", "publish_date", "category", "source_url")
CATEGORIES = {"ESG", "可持续", "双碳"}


def _is_valid_amount(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    number = float(value)
    return math.isfinite(number) and number >= 0


def _is_valid_url(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _canonical_url(value: str) -> str:
    parsed = urlparse(value.strip())
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{parsed.path.rstrip('/')}"


def validate_records(records: object) -> dict:
    if not isinstance(records, list):
        return {
            "ok": False,
            "total": 0,
            "valid": 0,
            "violations": [
                {"index": -1, "field": "root", "reason": "输入必须是记录数组"}
            ],
        }

    violations: list[dict] = []
    seen_urls: dict[str, int] = {}
    valid = 0

    for index, record in enumerate(records):
        before = len(violations)

        if not isinstance(record, dict):
            violations.append(
                {"index": index, "field": "record", "reason": "记录必须是对象"}
            )
            continue

        for field in REQUIRED_FIELDS:
            if field not in record:
                violations.append(
                    {"index": index, "field": field, "reason": "缺少必填字段"}
                )
            elif field in NON_EMPTY_FIELDS and (
                record[field] is None or str(record[field]).strip() == ""
            ):
                violations.append(
                    {"index": index, "field": field, "reason": "不能为空"}
                )

        amount = record.get("amount_wan")
        if amount is not None and not _is_valid_amount(amount):
            violations.append(
                {
                    "index": index,
                    "field": "amount_wan",
                    "reason": "金额必须是万元数字或 null",
                }
            )

        published = record.get("publish_date")
        if isinstance(published, str) and published:
            try:
                if len(published) != 10:
                    raise ValueError
                date.fromisoformat(published)
            except ValueError:
                violations.append(
                    {
                        "index": index,
                        "field": "publish_date",
                        "reason": "日期必须是有效的 YYYY-MM-DD",
                    }
                )
        elif published is not None:
            violations.append(
                {
                    "index": index,
                    "field": "publish_date",
                    "reason": "日期必须是有效的 YYYY-MM-DD",
                }
            )

        url = record.get("source_url")
        if not _is_valid_url(url):
            violations.append(
                {
                    "index": index,
                    "field": "source_url",
                    "reason": "必须是 http(s) URL",
                }
            )
        else:
            canonical = _canonical_url(url)
            if canonical in seen_urls:
                violations.append(
                    {
                        "index": index,
                        "field": "source_url",
                        "reason": f"重复：与第 {seen_urls[canonical]} 条相同",
                    }
                )
            else:
                seen_urls[canonical] = index

        category = record.get("category")
        if category is not None and category not in CATEGORIES:
            violations.append(
                {
                    "index": index,
                    "field": "category",
                    "reason": "只能是 ESG、可持续、双碳",
                }
            )

        if len(violations) == before:
            valid += 1

    return {
        "ok": not violations,
        "total": len(records),
        "valid": valid,
        "violations": violations,
    }


def _load_records(path: str) -> list:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, dict):
        data = data.get("records", [])
    if not isinstance(data, list):
        raise ValueError("输入必须是记录数组或包含 records 的对象")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="校验 ESG 招投标记录")
    parser.add_argument("--input", required=True, help="记录 JSON 文件")
    parser.add_argument("--output", default=None, help="校验结果输出路径")
    args = parser.parse_args(argv)

    try:
        records = _load_records(args.input)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"错误：无法读取 {args.input}: {exc}", file=sys.stderr)
        return 2

    result = validate_records(records)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
