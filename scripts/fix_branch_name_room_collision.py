from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.supabase_client import get_supabase_client
from app.crawler.naver_room_fetcher import NaverRoomFetcher
from app.core.name_utils import normalize_name_token


@dataclass
class Target:
    business_id: str
    before_name: str | None
    before_display_name: str | None
    room_names: list[str]
    candidate_name: str | None = None
    candidate_source: str | None = None
    candidate_reason: str | None = None



def is_placeholder_name(candidate: str, business_id: str) -> bool:
    lowered = candidate.strip().lower()
    return lowered in {business_id.lower(), f"business-{business_id.lower()}"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fix branch name/display_name collisions with room names for overlap targets."
    )
    parser.add_argument(
        "--overlap-csv",
        default="docs/api-quality-check-2026-03-04-branch-room-overlap.csv",
        help="CSV containing overlap targets (default: docs/api-quality-check-2026-03-04-branch-room-overlap.csv)",
    )
    parser.add_argument(
        "--log-dir",
        default="logs",
        help="Directory for dry-run/apply logs (default: logs)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply updates to DB. Without this flag, runs dry-run only.",
    )
    return parser.parse_args()


def load_target_business_ids(path: Path) -> list[str]:
    ids: list[str] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            bid = str(row.get("business_id", "")).strip()
            if bid and bid not in ids:
                ids.append(bid)
    return ids


def fetch_rows_by_business_ids(
    table: str,
    columns: str,
    business_ids: list[str],
    *,
    page_size: int = 1000,
) -> list[dict[str, Any]]:
    if not business_ids:
        return []
    supabase = get_supabase_client()
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        end = start + page_size - 1
        result = (
            supabase.table(table)
            .select(columns)
            .in_("business_id", business_ids)
            .range(start, end)
            .execute()
        )
        chunk = result.data or []
        rows.extend(chunk)
        if len(chunk) < page_size:
            break
        start += page_size
    return rows


async def collect_candidates(targets: list[Target]) -> None:
    fetcher = NaverRoomFetcher()
    async with httpx.AsyncClient() as client:
        for idx, target in enumerate(targets, start=1):
            try:
                business = await fetcher._fetch_business(client, target.business_id)  # noqa: SLF001
                if isinstance(business, dict):
                    for source, key in (
                        ("business.businessDisplayName", "businessDisplayName"),
                        ("business.name", "name"),
                    ):
                        raw = business.get(key)
                        if not isinstance(raw, str):
                            continue
                        candidate = re.sub(r"\s+", " ", raw).strip()
                        if not candidate:
                            continue
                        if is_placeholder_name(candidate, target.business_id):
                            continue
                        room_tokens = {normalize_name_token(x) for x in target.room_names if normalize_name_token(x)}
                        if normalize_name_token(candidate) in room_tokens:
                            continue
                        target.candidate_name = candidate
                        target.candidate_source = source
                        target.candidate_reason = "safe_business_name"
                        break

                if not target.candidate_name:
                    target.candidate_reason = "no_safe_candidate"
            except Exception as e:
                print(f"[candidate] fetch failed for {target.business_id}: {e}")
                target.candidate_name = None
                target.candidate_reason = "fetch_failure"

            if idx % 10 == 0:
                print(f"[candidate] progress {idx}/{len(targets)}")


def build_targets(business_ids: list[str]) -> list[Target]:
    branch_rows = fetch_rows_by_business_ids(
        table="branch",
        columns="business_id,name,display_name",
        business_ids=business_ids,
    )
    room_rows = fetch_rows_by_business_ids(
        table="room",
        columns="business_id,name",
        business_ids=business_ids,
    )

    branch_by_id = {str(row["business_id"]): row for row in branch_rows}
    room_names_by_business: dict[str, list[str]] = {}
    for row in room_rows:
        bid = str(row["business_id"])
        name = row.get("name")
        if isinstance(name, str) and name.strip():
            room_names_by_business.setdefault(bid, []).append(name.strip())

    targets: list[Target] = []
    for bid in business_ids:
        branch = branch_by_id.get(bid, {})
        targets.append(
            Target(
                business_id=bid,
                before_name=branch.get("name") if isinstance(branch, dict) else None,
                before_display_name=branch.get("display_name") if isinstance(branch, dict) else None,
                room_names=room_names_by_business.get(bid, []),
            )
        )
    return targets


def apply_updates(targets: list[Target]) -> list[dict[str, Any]]:
    supabase = get_supabase_client()
    applied: list[dict[str, Any]] = []
    for target in targets:
        if not target.candidate_name:
            continue
        payload = {"name": target.candidate_name, "display_name": target.candidate_name}
        supabase.table("branch").update(payload).eq("business_id", target.business_id).execute()
        applied.append(
            {
                "business_id": target.business_id,
                "before_name": target.before_name,
                "before_display_name": target.before_display_name,
                "after_name": target.candidate_name,
                "after_display_name": target.candidate_name,
                "source": target.candidate_source,
            }
        )
    return applied


def verify_updates(targets: list[Target]) -> list[dict[str, Any]]:
    business_ids = [t.business_id for t in targets if t.candidate_name]
    if not business_ids:
        return []

    branch_rows = fetch_rows_by_business_ids(
        table="branch",
        columns="business_id,name,display_name",
        business_ids=business_ids,
    )
    row_by_id = {str(row["business_id"]): row for row in branch_rows}

    verified: list[dict[str, Any]] = []
    for t in targets:
        if not t.candidate_name:
            continue
        row = row_by_id.get(t.business_id, {})
        after_name = row.get("name") if isinstance(row, dict) else None
        after_display = row.get("display_name") if isinstance(row, dict) else None
        room_tokens = {normalize_name_token(x) for x in t.room_names if normalize_name_token(x)}
        name_collision = normalize_name_token(after_name) in room_tokens if isinstance(after_name, str) else False
        display_collision = (
            normalize_name_token(after_display) in room_tokens if isinstance(after_display, str) else False
        )
        verified.append(
            {
                "business_id": t.business_id,
                "expected_name": t.candidate_name,
                "after_name": after_name,
                "after_display_name": after_display,
                "matches_expected": after_name == t.candidate_name and after_display == t.candidate_name,
                "name_collides_with_room": name_collision or display_collision,
            }
        )
    return verified


def to_log_payload(
    *,
    mode: str,
    targets: list[Target],
    applied: list[dict[str, Any]],
    verified: list[dict[str, Any]],
) -> dict[str, Any]:
    unresolved = [
        {
            "business_id": t.business_id,
            "before_name": t.before_name,
            "before_display_name": t.before_display_name,
            "reason": t.candidate_reason,
        }
        for t in targets
        if not t.candidate_name
    ]
    mismatched = [row for row in verified if not row["matches_expected"]]
    still_collided = [row for row in verified if row["name_collides_with_room"]]

    return {
        "summary": {
            "executed_at": datetime.now().isoformat(),
            "mode": mode,
            "target_count": len(targets),
            "candidate_ready_count": sum(1 for t in targets if t.candidate_name),
            "unresolved_count": len(unresolved),
            "applied_count": len(applied),
            "verified_count": len(verified),
            "verified_match_count": sum(1 for row in verified if row["matches_expected"]),
            "verified_still_collided_count": len(still_collided),
            "verified_mismatch_count": len(mismatched),
        },
        "planned_updates": [
            {
                "business_id": t.business_id,
                "before_name": t.before_name,
                "before_display_name": t.before_display_name,
                "candidate_name": t.candidate_name,
                "candidate_source": t.candidate_source,
                "candidate_reason": t.candidate_reason,
            }
            for t in targets
            if t.candidate_name
        ],
        "applied": applied,
        "verified": verified,
        "unresolved": unresolved,
    }


def main() -> None:
    args = parse_args()
    overlap_csv = Path(args.overlap_csv)
    if not overlap_csv.exists():
        raise FileNotFoundError(f"overlap csv not found: {overlap_csv}")

    business_ids = load_target_business_ids(overlap_csv)
    targets = build_targets(business_ids)

    asyncio.run(collect_candidates(targets))

    mode = "branch_name_collision_fix_applied" if args.apply else "branch_name_collision_fix_dry_run"
    applied: list[dict[str, Any]] = []
    verified: list[dict[str, Any]] = []

    if args.apply:
        applied = apply_updates(targets)
        verified = verify_updates(targets)

    payload = to_log_payload(mode=mode, targets=targets, applied=applied, verified=verified)

    log_dir = Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    log_path = log_dir / f"{mode}_{ts}.json"
    log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"mode": mode, "log_path": str(log_path), "summary": payload["summary"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
