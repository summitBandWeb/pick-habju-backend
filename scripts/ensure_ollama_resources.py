import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import httpx


def list_models() -> List[str]:
    try:
        resp = httpx.get("http://localhost:11434/api/tags", timeout=10)
        resp.raise_for_status()
        models = resp.json().get("models", [])
        return [m.get("name", "") for m in models if m.get("name")]
    except Exception:
        return []


def pull_model(model: str) -> Tuple[bool, str]:
    try:
        proc = subprocess.run(
            ["ollama", "pull", model],
            check=False,
            capture_output=True,
            text=True,
        )
        ok = proc.returncode == 0
        msg = (proc.stdout or proc.stderr or "").strip()
        return ok, msg
    except Exception as exc:
        return False, str(exc)


def quick_generate(model: str) -> Tuple[bool, str]:
    payload = {
        "model": model,
        "prompt": 'Return JSON: {"ok": true}',
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.0, "num_predict": 64},
    }
    try:
        resp = httpx.post("http://localhost:11434/api/generate", json=payload, timeout=60)
        if resp.status_code != 200:
            return False, f"status={resp.status_code}, body={resp.text[:200]}"
        return True, "ok"
    except Exception as exc:
        return False, str(exc)


def detect_available_memory_mb() -> Optional[int]:
    try:
        import psutil  # type: ignore

        return int(psutil.virtual_memory().available / (1024 * 1024))
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check Ollama model resources and suggest a stable model."
    )
    parser.add_argument("--primary", default=os.getenv("OLLAMA_MODEL", "llama3.1:8b"))
    parser.add_argument("--fallback", default="llama3.2:3b")
    parser.add_argument("--pull-missing", action="store_true")
    parser.add_argument("--report-path", default="")
    args = parser.parse_args()

    models_before = list_models()
    actions: List[Dict[str, str]] = []

    for target in [args.primary, args.fallback]:
        if target not in models_before and args.pull_missing:
            ok, msg = pull_model(target)
            actions.append(
                {
                    "action": "pull",
                    "model": target,
                    "status": "success" if ok else "failed",
                    "message": msg[:500],
                }
            )

    models_after = list_models()

    primary_ok, primary_msg = quick_generate(args.primary)
    chosen_model = args.primary
    fallback_ok = False
    fallback_msg = "not_tested"

    if not primary_ok:
        fallback_ok, fallback_msg = quick_generate(args.fallback)
        if fallback_ok:
            chosen_model = args.fallback

    report = {
        "checked_at": datetime.now().isoformat(),
        "available_memory_mb": detect_available_memory_mb(),
        "primary_model": args.primary,
        "fallback_model": args.fallback,
        "models_before": models_before,
        "models_after": models_after,
        "actions": actions,
        "primary_health": {"ok": primary_ok, "message": primary_msg},
        "fallback_health": {"ok": fallback_ok, "message": fallback_msg},
        "recommended_model": chosen_model,
        "windows_set_command": f"set OLLAMA_MODEL={chosen_model}",
        "powershell_set_command": f"$env:OLLAMA_MODEL='{chosen_model}'",
    }

    print(json.dumps(report, ensure_ascii=False, indent=2))

    if args.report_path:
        path = Path(args.report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    return 0


if __name__ == "__main__":
    sys.exit(main())
