from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _post_json(url: str, payload: dict) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=240) as res:  # nosec B310
            body = res.read().decode("utf-8", errors="ignore")
            return int(res.status), json.loads(body) if body else {}
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        try:
            return int(exc.code), json.loads(body) if body else {"error": body}
        except Exception:  # noqa: BLE001
            return int(exc.code), {"error": body}
    except URLError as exc:
        return 0, {"error": str(exc)}


def run_benchmark(base_url: str, runs: int, start_seed: int, rows: int) -> dict:
    endpoint = f"{base_url.rstrip('/')}/admin/data/benchmark-random"
    details: list[dict] = []

    accuracy_values: list[float] = []
    cls_ms: list[float] = []
    stock_ms: list[float] = []
    recipe_ms: list[float] = []
    pred_ms: list[float] = []
    checks_ok = 0

    for i in range(runs):
        seed = start_seed + i
        status, body = _post_json(endpoint, {"rows": rows, "seed": seed})
        ok = status == 200 and bool(body.get("ok", False))
        if ok:
            checks_ok += 1
            accuracy_values.append(float((body.get("classification_eval", {}) or {}).get("accuracy", 0.0)))
            perf = body.get("tool_performance_ms", {}) or {}
            cls_ms.append(float(perf.get("classification_ms", 0.0)))
            stock_ms.append(float(perf.get("stock_ms", 0.0)))
            recipe_ms.append(float(perf.get("recipe_ms", 0.0)))
            pred_ms.append(float(perf.get("prediction_ms", 0.0)))

        details.append(
            {
                "run_index": i + 1,
                "seed": seed,
                "http_status": status,
                "ok": ok,
                "classification_eval": body.get("classification_eval", {}),
                "tool_performance_ms": body.get("tool_performance_ms", {}),
                "sanity_checks": body.get("sanity_checks", {}),
                "error": body.get("detail") or body.get("error") or "",
            }
        )

    summary = {
        "runs": runs,
        "successful_runs": checks_ok,
        "success_rate": round((checks_ok / runs), 4) if runs else 0.0,
        "classification_accuracy_avg": round(mean(accuracy_values), 4) if accuracy_values else 0.0,
        "latency_avg_ms": {
            "classification_ms": round(mean(cls_ms), 3) if cls_ms else 0.0,
            "stock_ms": round(mean(stock_ms), 3) if stock_ms else 0.0,
            "recipe_ms": round(mean(recipe_ms), 3) if recipe_ms else 0.0,
            "prediction_ms": round(mean(pred_ms), 3) if pred_ms else 0.0,
        },
    }

    return {
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "base_url": base_url,
        "config": {"runs": runs, "start_seed": start_seed, "rows": rows},
        "summary": summary,
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run multi-seed random stock benchmark and save QA report.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8030", help="Harness backend base URL")
    parser.add_argument("--runs", type=int, default=10, help="Number of benchmark runs")
    parser.add_argument("--start-seed", type=int, default=42, help="First seed")
    parser.add_argument("--rows", type=int, default=1500, help="Rows generated per run")
    args = parser.parse_args()

    report = run_benchmark(
        base_url=args.base_url,
        runs=max(1, int(args.runs)),
        start_seed=int(args.start_seed),
        rows=max(100, int(args.rows)),
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(__file__).parent / f"qa_random_benchmark_{stamp}.json"
    out.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    print(json.dumps({"report_path": str(out), "summary": report.get("summary", {})}, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()

