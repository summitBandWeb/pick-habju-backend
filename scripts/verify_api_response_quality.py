from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests


@dataclass(frozen=True)
class AreaBox:
    key: str
    label: str
    sw_lat: float
    sw_lng: float
    ne_lat: float
    ne_lng: float

    def to_query(self) -> dict[str, float]:
        return {
            "swLat": self.sw_lat,
            "swLng": self.sw_lng,
            "neLat": self.ne_lat,
            "neLng": self.ne_lng,
        }


DEFAULT_AREAS: tuple[AreaBox, ...] = (
    AreaBox(
        key="isoo",
        label="이수",
        sw_lat=37.477196,
        sw_lng=126.972005,
        ne_lat=37.493196,
        ne_lng=126.99120500000001,
    ),
    AreaBox(
        key="sadang",
        label="사당",
        sw_lat=37.4698,
        sw_lng=126.9720,
        ne_lat=37.4858,
        ne_lng=126.9910,
    ),
    AreaBox(
        key="hongdae",
        label="홍대입구",
        sw_lat=37.5478,
        sw_lng=126.9150,
        ne_lat=37.5638,
        ne_lng=126.9360,
    ),
    AreaBox(
        key="sinchon",
        label="신촌",
        sw_lat=37.5470,
        sw_lng=126.9280,
        ne_lat=37.5630,
        ne_lng=126.9480,
    ),
    AreaBox(
        key="seoul_all",
        label="서울광역",
        sw_lat=37.4300,
        sw_lng=126.8200,
        ne_lat=37.7000,
        ne_lng=127.1900,
    ),
)

PHONE_PATTERN = re.compile(r"^\d{2,4}-\d{3,4}-\d{4}$")
PRODUCTION_HOSTS = {"api.pickhabju.com", "pickhabju.com", "www.pickhabju.com"}


def parse_offsets(raw: str) -> list[int]:
    parts = [x.strip() for x in raw.split(",") if x.strip()]
    if not parts:
        raise ValueError("date offsets are empty")
    return [int(x) for x in parts]


def parse_time_ranges(raw: str) -> list[tuple[str, str]]:
    items = [x.strip() for x in raw.split(",") if x.strip()]
    if not items:
        raise ValueError("time ranges are empty")
    ranges: list[tuple[str, str]] = []
    for item in items:
        if "-" not in item:
            raise ValueError(f"invalid time range: {item}")
        start, end = item.split("-", 1)
        start = start.strip()
        end = end.strip()
        if not start or not end:
            raise ValueError(f"invalid time range: {item}")
        ranges.append((start, end))
    return ranges


def parse_capacities(raw: str) -> list[int]:
    parts = [x.strip() for x in raw.split(",") if x.strip()]
    if not parts:
        raise ValueError("capacities are empty")
    return [int(x) for x in parts]


def is_production_like_url(base_url: str) -> bool:
    parsed = urlparse(base_url if "://" in base_url else f"https://{base_url}")
    host = (parsed.hostname or "").lower()
    return host in PRODUCTION_HOSTS or "prod" in host


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify API response quality for availability/favorites endpoints and "
            "generate CSV/JSON/Markdown reports."
        )
    )
    parser.add_argument(
        "--base-url",
        default="https://alpha-api.pickhabju.com",
        help="API base URL (default: https://alpha-api.pickhabju.com)",
    )
    parser.add_argument(
        "--output-dir",
        default="docs",
        help="Directory where report files are written (default: docs)",
    )
    parser.add_argument(
        "--output-prefix",
        default=f"api-quality-check-{date.today().isoformat()}",
        help="Output file prefix (default: api-quality-check-YYYY-MM-DD)",
    )
    parser.add_argument(
        "--device-id",
        default="550e8400-e29b-41d4-a716-446655440000",
        help=(
            "X-Device-Id for favorites endpoint checks "
            "(default is test UUID: 550e8400-e29b-41d4-a716-446655440000)"
        ),
    )
    parser.add_argument(
        "--date-offsets",
        default="1,7,14",
        help="Comma-separated date offsets from today (default: 1,7,14)",
    )
    parser.add_argument(
        "--time-ranges",
        default="01:00-03:00,10:00-12:00,19:00-21:00",
        help="Comma-separated HH:MM-HH:MM ranges (default: 01:00-03:00,10:00-12:00,19:00-21:00)",
    )
    parser.add_argument(
        "--capacities",
        default="2,8,12",
        help="Comma-separated capacities (default: 2,8,12)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=25.0,
        help="HTTP timeout seconds per request (default: 25)",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=1,
        help="Retry count for transport errors (default: 1)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Parallel workers for availability matrix (default: 1)",
    )
    parser.add_argument(
        "--skip-favorites-roundtrip",
        action="store_true",
        help="Skip the favorites put/delete roundtrip checks",
    )
    return parser.parse_args()


def request_json(
    session: requests.Session,
    method: str,
    url: str,
    *,
    timeout: float,
    retries: int,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    last_error = ""
    for attempt in range(retries + 1):
        try:
            response = session.request(
                method=method,
                url=url,
                params=params,
                headers=headers,
                timeout=timeout,
            )
            try:
                payload = response.json()
            except ValueError:
                payload = None
            return {
                "ok": True,
                "status": response.status_code,
                "json": payload,
                "text": response.text,
                "attempt": attempt + 1,
            }
        except requests.RequestException as exc:  # pragma: no cover - depends on network
            last_error = str(exc)
    return {
        "ok": False,
        "status": None,
        "json": None,
        "text": last_error,
        "attempt": retries + 1,
    }


def is_envelope(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    required = {"isSuccess", "code", "message", "result"}
    return required.issubset(payload.keys())


def to_iso_dates(offsets: list[int]) -> list[str]:
    return [(date.today() + timedelta(days=offset)).isoformat() for offset in offsets]


def build_tasks(
    areas: list[AreaBox],
    dates: list[str],
    time_ranges: list[tuple[str, str]],
    capacities: list[int],
) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for area in areas:
        for requested_date in dates:
            for start_hour, end_hour in time_ranges:
                for capacity in capacities:
                    task = {
                        "area_key": area.key,
                        "area_label": area.label,
                        "date": requested_date,
                        "start_hour": start_hour,
                        "end_hour": end_hour,
                        "capacity": capacity,
                    }
                    task.update(area.to_query())
                    tasks.append(task)
    return tasks


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def dump_markdown(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def make_report_markdown(summary: dict[str, Any], files: dict[str, str]) -> str:
    endpoint = summary["endpoint_checks"]
    avail = summary["availability_summary"]
    coverage = summary["coverage_summary"]
    phone = summary["field_quality"]["phone"]
    display_name = summary["field_quality"]["display_name"]

    return "\n".join(
        [
            f"# API Quality Check Report ({summary['generated_at']})",
            "",
            "## Matrix",
            f"- Total requests: {avail['total_requests']}",
            f"- Dates: {', '.join(summary['matrix']['dates'])}",
            f"- Time ranges: {', '.join(summary['matrix']['time_ranges'])}",
            f"- Capacities: {', '.join(str(x) for x in summary['matrix']['capacities'])}",
            f"- Areas: {', '.join(summary['matrix']['areas'])}",
            "",
            "## Endpoint Snapshot",
            f"- `GET /ping`: {endpoint['GET /ping']['status']}",
            f"- `GET /health`: {endpoint['GET /health']['status']}",
            f"- `GET /api/test/success`: {endpoint['GET /api/test/success']['status']}",
            f"- `GET /api/test/error?status_code=400`: {endpoint['GET /api/test/error?status_code=400']['status']}",
            f"- `GET /api/test/server-error`: {endpoint['GET /api/test/server-error']['status']}",
            f"- `GET /api/favorites` (missing header): {endpoint['GET /api/favorites (missing header)']['status']}",
            f"- `GET /api/favorites` (invalid header): {endpoint['GET /api/favorites (invalid header)']['status']}",
            f"- `GET /api/favorites` (valid header): {endpoint['GET /api/favorites (valid header)']['status']}",
            "",
            "## Availability Quality",
            f"- HTTP status distribution: {avail['status_distribution']}",
            f"- Transport error count: {avail['transport_error_count']}",
            f"- Non-200 count: {avail['non_200_count']}",
            f"- Envelope invalid count: {avail['envelope_invalid_count']}",
            f"- `isSuccess == false` count: {avail['is_success_false_count']}",
            f"- `available_biz_item_ids` mismatch requests: {avail['available_ids_mismatch_request_count']}",
            f"- `branch` includes room name count: {avail['branch_contains_room_name_count']}",
            "",
            "## Field Quality",
            f"- `phone_number`: null={phone['null_count']}, non_null={phone['non_null_count']}, valid_format={phone['valid_format_count']}, invalid_format={phone['invalid_format_count']}",
            f"- `display_name`: null={display_name['null_count']}, non_null={display_name['non_null_count']}",
            "",
            "## Coverage",
            f"- Local union business IDs (이수/사당/홍대입구/신촌): {coverage['local_union_count']}",
            f"- 서울광역 business IDs: {coverage['seoul_all_count']}",
            f"- 서울광역 only business IDs: {coverage['seoul_all_only_count']}",
            "",
            "## Output Files",
            f"- Summary JSON: `{files['summary_json']}`",
            f"- Mismatch CSV: `{files['mismatch_csv']}`",
            f"- Coverage CSV: `{files['coverage_csv']}`",
            f"- Branch/Room overlap CSV: `{files['branch_room_overlap_csv']}`",
            f"- Markdown report: `{files['report_md']}`",
            "",
        ]
    )


def main() -> None:
    args = parse_args()

    date_offsets = parse_offsets(args.date_offsets)
    time_ranges = parse_time_ranges(args.time_ranges)
    capacities = parse_capacities(args.capacities)

    requested_dates = to_iso_dates(date_offsets)
    areas = list(DEFAULT_AREAS)
    tasks = build_tasks(
        areas=areas,
        dates=requested_dates,
        time_ranges=time_ranges,
        capacities=capacities,
    )

    base = args.base_url.rstrip("/")
    output_dir = Path(args.output_dir)
    output_prefix = args.output_prefix

    summary_json_path = output_dir / f"{output_prefix}-summary.json"
    mismatch_csv_path = output_dir / f"{output_prefix}-mismatch.csv"
    coverage_csv_path = output_dir / f"{output_prefix}-coverage.csv"
    branch_room_overlap_csv_path = output_dir / f"{output_prefix}-branch-room-overlap.csv"
    report_md_path = output_dir / f"{output_prefix}-report.md"

    session = requests.Session()

    endpoint_checks: dict[str, dict[str, Any]] = {}
    for endpoint in [
        ("GET /ping", "GET", "/ping", None, None),
        ("GET /health", "GET", "/health", None, None),
        ("GET /api/test/success", "GET", "/api/test/success", None, None),
        (
            "GET /api/test/error?status_code=400",
            "GET",
            "/api/test/error",
            {"status_code": 400},
            None,
        ),
        ("GET /api/test/server-error", "GET", "/api/test/server-error", None, None),
    ]:
        key, method, path, params, headers = endpoint
        result = request_json(
            session=session,
            method=method,
            url=f"{base}{path}",
            timeout=args.timeout,
            retries=args.retries,
            params=params,
            headers=headers,
        )
        endpoint_checks[key] = {
            "status": result["status"],
            "transport_ok": result["ok"],
            "envelope_ok": is_envelope(result["json"]),
            "code": result["json"].get("code") if isinstance(result["json"], dict) else None,
            "isSuccess": result["json"].get("isSuccess") if isinstance(result["json"], dict) else None,
        }

    favorites_missing = request_json(
        session=session,
        method="GET",
        url=f"{base}/api/favorites",
        timeout=args.timeout,
        retries=args.retries,
    )
    favorites_invalid = request_json(
        session=session,
        method="GET",
        url=f"{base}/api/favorites",
        timeout=args.timeout,
        retries=args.retries,
        headers={"X-Device-Id": "invalid-device-id"},
    )
    favorites_valid = request_json(
        session=session,
        method="GET",
        url=f"{base}/api/favorites",
        timeout=args.timeout,
        retries=args.retries,
        headers={"X-Device-Id": args.device_id},
    )

    endpoint_checks["GET /api/favorites (missing header)"] = {
        "status": favorites_missing["status"],
        "transport_ok": favorites_missing["ok"],
        "envelope_ok": is_envelope(favorites_missing["json"]),
        "code": favorites_missing["json"].get("code")
        if isinstance(favorites_missing["json"], dict)
        else None,
    }
    endpoint_checks["GET /api/favorites (invalid header)"] = {
        "status": favorites_invalid["status"],
        "transport_ok": favorites_invalid["ok"],
        "envelope_ok": is_envelope(favorites_invalid["json"]),
        "code": favorites_invalid["json"].get("code")
        if isinstance(favorites_invalid["json"], dict)
        else None,
    }
    endpoint_checks["GET /api/favorites (valid header)"] = {
        "status": favorites_valid["status"],
        "transport_ok": favorites_valid["ok"],
        "envelope_ok": is_envelope(favorites_valid["json"]),
        "code": favorites_valid["json"].get("code")
        if isinstance(favorites_valid["json"], dict)
        else None,
        "favorite_count": len(
            (favorites_valid["json"] or {}).get("result", {}).get("biz_item_ids", [])
        )
        if isinstance((favorites_valid["json"] or {}).get("result", {}), dict)
        else None,
    }

    status_distribution = Counter()
    transport_error_count = 0
    non_200_count = 0
    envelope_invalid_count = 0
    is_success_false_count = 0

    area_stats: dict[str, dict[str, Any]] = {
        area.key: {
            "label": area.label,
            "requests": 0,
            "success_responses": 0,
            "empty_responses": 0,
            "business_ids": set(),
            "biz_item_ids": set(),
        }
        for area in areas
    }

    mismatch_rows: list[dict[str, Any]] = []
    branch_room_overlap_rows: dict[tuple[str, str, str], dict[str, Any]] = {}
    transport_error_samples: list[dict[str, Any]] = []

    phone_null_count = 0
    phone_non_null_count = 0
    phone_valid_format_count = 0
    phone_invalid_format_count = 0
    display_name_null_count = 0
    display_name_non_null_count = 0

    branch_contains_room_name_count = 0
    available_ids_mismatch_request_count = 0

    business_name_by_id: dict[str, str] = {}
    first_favorite_sample: dict[str, str] | None = None

    def fetch_task(task: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        with requests.Session() as local_session:
            result = request_json(
                session=local_session,
                method="GET",
                url=f"{base}/api/rooms/availability/",
                timeout=args.timeout,
                retries=args.retries,
                params=task,
            )
        return task, result

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = [executor.submit(fetch_task, task) for task in tasks]
        for future in as_completed(futures):
            task, result = future.result()
            area_key = task["area_key"]
            stats = area_stats[area_key]
            stats["requests"] += 1
            status_distribution[str(result["status"])] += 1

            if not result["ok"]:
                transport_error_count += 1
                if len(transport_error_samples) < 20:
                    transport_error_samples.append(
                        {
                            "area_key": area_key,
                            "area_label": task["area_label"],
                            "date": task["date"],
                            "start_hour": task["start_hour"],
                            "end_hour": task["end_hour"],
                            "capacity": task["capacity"],
                            "error": result["text"],
                        }
                    )
                continue

            if result["status"] != 200:
                non_200_count += 1
                continue

            payload = result["json"]
            if not is_envelope(payload):
                envelope_invalid_count += 1
                continue

            if not payload.get("isSuccess"):
                is_success_false_count += 1
                continue

            stats["success_responses"] += 1

            response_result = payload.get("result") or {}
            branches = response_result.get("branches") or []
            available_ids = set(response_result.get("available_biz_item_ids") or [])
            room_true_ids: set[str] = set()

            if not branches:
                stats["empty_responses"] += 1

            for branch in branches:
                business_id = branch.get("business_id")
                business_id_str = str(business_id) if business_id is not None else ""
                if business_id_str:
                    stats["business_ids"].add(business_id_str)
                    if business_id_str not in business_name_by_id:
                        business_name_by_id[business_id_str] = str(branch.get("branch") or "")

                branch_name = str(branch.get("branch") or "").strip()
                display_name = branch.get("display_name")
                phone_number = branch.get("phone_number")
                rooms = branch.get("rooms") or []

                if display_name is None or (isinstance(display_name, str) and not display_name.strip()):
                    display_name_null_count += 1
                else:
                    display_name_non_null_count += 1

                if phone_number is None or (isinstance(phone_number, str) and not phone_number.strip()):
                    phone_null_count += 1
                else:
                    phone_non_null_count += 1
                    phone_text = str(phone_number).strip()
                    if PHONE_PATTERN.match(phone_text):
                        phone_valid_format_count += 1
                    else:
                        phone_invalid_format_count += 1

                for room in rooms:
                    room_id = room.get("biz_item_id")
                    room_id_str = str(room_id) if room_id is not None else ""
                    if room_id_str:
                        stats["biz_item_ids"].add(room_id_str)
                        if room.get("available") is True:
                            room_true_ids.add(room_id_str)

                    room_name = str(room.get("name") or "").strip()
                    if room_name and branch_name and room_name in branch_name:
                        branch_contains_room_name_count += 1
                        dedupe_key = (area_key, business_id_str, room_name)
                        if dedupe_key not in branch_room_overlap_rows:
                            branch_room_overlap_rows[dedupe_key] = {
                                "area_key": area_key,
                                "area_label": task["area_label"],
                                "business_id": business_id_str,
                                "branch_name": branch_name,
                                "room_name": room_name,
                            }

                    if first_favorite_sample is None and business_id_str and room_id_str:
                        first_favorite_sample = {
                            "business_id": business_id_str,
                            "biz_item_id": room_id_str,
                        }

            if available_ids and not available_ids.issubset(room_true_ids):
                available_ids_mismatch_request_count += 1
                extras = sorted(available_ids - room_true_ids)
                mismatch_rows.append(
                    {
                        "area_key": area_key,
                        "area_label": task["area_label"],
                        "date": task["date"],
                        "start_hour": task["start_hour"],
                        "end_hour": task["end_hour"],
                        "capacity": task["capacity"],
                        "extra_ids_count": len(extras),
                        "extra_ids": ",".join(extras),
                    }
                )

    favorites_roundtrip: dict[str, Any] = {"executed": False}
    should_run_favorites_roundtrip = bool(first_favorite_sample) and not args.skip_favorites_roundtrip

    if args.skip_favorites_roundtrip:
        favorites_roundtrip["skipped_reason"] = "flag_enabled"
    elif not first_favorite_sample:
        favorites_roundtrip["skipped_reason"] = "no_sample_available"

    if should_run_favorites_roundtrip and is_production_like_url(base):
        print(
            "[confirm] favorites roundtrip performs PUT/DELETE against live data. "
            f"base_url={base}. Continue? [y/N]: ",
            end="",
        )
        try:
            confirm = input().strip().lower()
        except EOFError:
            confirm = ""
        if confirm not in {"y", "yes"}:
            should_run_favorites_roundtrip = False
            favorites_roundtrip["skipped_reason"] = "production_confirmation_declined"
            print("Skipped favorites roundtrip: production confirmation was not granted.")

    if should_run_favorites_roundtrip:
        biz_item_id = first_favorite_sample["biz_item_id"]
        business_id = first_favorite_sample["business_id"]

        before = request_json(
            session=session,
            method="GET",
            url=f"{base}/api/favorites",
            timeout=args.timeout,
            retries=args.retries,
            headers={"X-Device-Id": args.device_id},
        )
        added = request_json(
            session=session,
            method="PUT",
            url=f"{base}/api/favorites/{biz_item_id}",
            timeout=args.timeout,
            retries=args.retries,
            params={"business_id": business_id},
            headers={"X-Device-Id": args.device_id},
        )
        after_add = request_json(
            session=session,
            method="GET",
            url=f"{base}/api/favorites",
            timeout=args.timeout,
            retries=args.retries,
            headers={"X-Device-Id": args.device_id},
        )
        deleted = request_json(
            session=session,
            method="DELETE",
            url=f"{base}/api/favorites/{biz_item_id}",
            timeout=args.timeout,
            retries=args.retries,
            params={"business_id": business_id},
            headers={"X-Device-Id": args.device_id},
        )
        after_delete = request_json(
            session=session,
            method="GET",
            url=f"{base}/api/favorites",
            timeout=args.timeout,
            retries=args.retries,
            headers={"X-Device-Id": args.device_id},
        )
        missing_business_id = request_json(
            session=session,
            method="PUT",
            url=f"{base}/api/favorites/{biz_item_id}",
            timeout=args.timeout,
            retries=args.retries,
            headers={"X-Device-Id": args.device_id},
        )

        def as_fav_set(resp: dict[str, Any]) -> set[str]:
            payload = resp.get("json")
            if not isinstance(payload, dict):
                return set()
            result = payload.get("result")
            if not isinstance(result, dict):
                return set()
            ids = result.get("biz_item_ids")
            if not isinstance(ids, list):
                return set()
            return {str(item) for item in ids}

        before_set = as_fav_set(before)
        after_add_set = as_fav_set(after_add)
        after_delete_set = as_fav_set(after_delete)

        favorites_roundtrip = {
            "executed": True,
            "sample": first_favorite_sample,
            "before_count": len(before_set),
            "after_add_count": len(after_add_set),
            "after_delete_count": len(after_delete_set),
            "add_status": added["status"],
            "delete_status": deleted["status"],
            "add_envelope_ok": is_envelope(added["json"]),
            "delete_envelope_ok": is_envelope(deleted["json"]),
            "added_present_after_add": biz_item_id in after_add_set,
            "removed_after_delete": biz_item_id not in after_delete_set,
            "missing_business_id_status": missing_business_id["status"],
            "missing_business_id_code": (
                missing_business_id["json"].get("code")
                if isinstance(missing_business_id["json"], dict)
                else None
            ),
        }

    coverage_rows: list[dict[str, Any]] = []
    local_area_keys = [area.key for area in areas if area.key != "seoul_all"]
    local_union = set()
    for area_key in local_area_keys:
        local_union |= area_stats[area_key]["business_ids"]
    seoul_all_set = area_stats["seoul_all"]["business_ids"]
    all_business_ids = sorted(set().union(*[stats["business_ids"] for stats in area_stats.values()]))
    for business_id in all_business_ids:
        row = {
            "business_id": business_id,
            "branch_name": business_name_by_id.get(business_id, ""),
        }
        for area in areas:
            row[f"in_{area.key}"] = "Y" if business_id in area_stats[area.key]["business_ids"] else "N"
        row["seoul_all_only"] = (
            "Y"
            if business_id in seoul_all_set and business_id not in local_union
            else "N"
        )
        coverage_rows.append(row)

    area_summary = {
        area.key: {
            "label": area.label,
            "requests": area_stats[area.key]["requests"],
            "success_responses": area_stats[area.key]["success_responses"],
            "empty_responses": area_stats[area.key]["empty_responses"],
            "unique_business_ids": len(area_stats[area.key]["business_ids"]),
            "unique_biz_item_ids": len(area_stats[area.key]["biz_item_ids"]),
        }
        for area in areas
    }

    summary: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "base_url": base,
        "matrix": {
            "dates": requested_dates,
            "time_ranges": [f"{start}-{end}" for start, end in time_ranges],
            "capacities": capacities,
            "areas": [area.label for area in areas],
            "workers": args.workers,
            "timeout_seconds": args.timeout,
            "retries": args.retries,
        },
        "endpoint_checks": endpoint_checks,
        "availability_summary": {
            "total_requests": len(tasks),
            "status_distribution": dict(status_distribution),
            "transport_error_count": transport_error_count,
            "non_200_count": non_200_count,
            "envelope_invalid_count": envelope_invalid_count,
            "is_success_false_count": is_success_false_count,
            "available_ids_mismatch_request_count": available_ids_mismatch_request_count,
            "branch_contains_room_name_count": branch_contains_room_name_count,
            "area_stats": area_summary,
            "transport_error_samples": transport_error_samples,
        },
        "field_quality": {
            "phone": {
                "null_count": phone_null_count,
                "non_null_count": phone_non_null_count,
                "valid_format_count": phone_valid_format_count,
                "invalid_format_count": phone_invalid_format_count,
            },
            "display_name": {
                "null_count": display_name_null_count,
                "non_null_count": display_name_non_null_count,
            },
        },
        "coverage_summary": {
            "local_union_count": len(local_union),
            "seoul_all_count": len(seoul_all_set),
            "seoul_all_only_count": len(seoul_all_set - local_union),
            "seoul_all_only_business_ids": sorted(seoul_all_set - local_union),
        },
        "favorites_roundtrip": favorites_roundtrip,
        "output_files": {
            "summary_json": str(summary_json_path),
            "mismatch_csv": str(mismatch_csv_path),
            "coverage_csv": str(coverage_csv_path),
            "branch_room_overlap_csv": str(branch_room_overlap_csv_path),
            "report_md": str(report_md_path),
        },
    }

    mismatch_fieldnames = [
        "area_key",
        "area_label",
        "date",
        "start_hour",
        "end_hour",
        "capacity",
        "extra_ids_count",
        "extra_ids",
    ]
    write_csv(mismatch_csv_path, mismatch_rows, mismatch_fieldnames)

    coverage_fieldnames = ["business_id", "branch_name"] + [
        f"in_{area.key}" for area in areas
    ] + ["seoul_all_only"]
    write_csv(coverage_csv_path, coverage_rows, coverage_fieldnames)

    branch_overlap_rows = sorted(
        branch_room_overlap_rows.values(),
        key=lambda x: (x["area_key"], x["business_id"], x["room_name"]),
    )
    branch_overlap_fieldnames = [
        "area_key",
        "area_label",
        "business_id",
        "branch_name",
        "room_name",
    ]
    write_csv(branch_room_overlap_csv_path, branch_overlap_rows, branch_overlap_fieldnames)

    dump_json(summary_json_path, summary)
    markdown = make_report_markdown(
        summary=summary,
        files={
            "summary_json": str(summary_json_path),
            "mismatch_csv": str(mismatch_csv_path),
            "coverage_csv": str(coverage_csv_path),
            "branch_room_overlap_csv": str(branch_room_overlap_csv_path),
            "report_md": str(report_md_path),
        },
    )
    dump_markdown(report_md_path, markdown)

    print(f"Wrote {summary_json_path}")
    print(f"Wrote {mismatch_csv_path}")
    print(f"Wrote {coverage_csv_path}")
    print(f"Wrote {branch_room_overlap_csv_path}")
    print(f"Wrote {report_md_path}")

    session.close()


if __name__ == "__main__":
    main()
