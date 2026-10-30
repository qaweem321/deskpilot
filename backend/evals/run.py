"""Evaluate the assistant against evals/cases.jsonl with the configured model.

Each case runs in a fresh database through the real HTTP API. Confirmations are approved
(or declined when the case says "approve": false). Results go to evals/results/.

    uv run python -m evals.run                     # model from .env
    uv run python -m evals.run --router keywords   # compare routers
    uv run python -m evals.run --only kb-          # a subset
"""

import argparse
import json
import statistics
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from app.rag.store import FastEmbedder
from app.seed import DEMO_PASSWORD
from app.services.actions import ACTIONS

HERE = Path(__file__).parent
HEADERS = {"X-Requested-With": "deskpilot"}


def read_events(response) -> list[dict]:  # noqa: ANN001
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


def args_match(expected: dict, actual: dict) -> bool:
    for key, value in expected.items():
        got = actual.get(key)
        if isinstance(value, int | float):
            try:
                if float(got) != float(value):  # type: ignore[arg-type]
                    return False
            except (TypeError, ValueError):
                return False
        elif str(got or "").lower() != str(value).lower():
            return False
    return True


def run_case(case: dict, embedder, router_mode: str | None) -> dict:  # noqa: ANN001, C901
    with tempfile.TemporaryDirectory() as tmp:
        overrides = {"database_url": f"sqlite:///{tmp}/e.db", "checkpoint_path": f"{tmp}/c.db"}
        if router_mode:
            overrides["router_mode"] = router_mode
        settings = get_settings().model_copy(update=overrides)
        app = create_app(settings, embedder=embedder)
        with TestClient(app, headers=HEADERS) as client:
            client.post(
                "/api/auth/login", json={"email": f"{case['role']}@deskpilot.test", "password": DEMO_PASSWORD}
            ).raise_for_status()
            start = time.perf_counter()
            evts = read_events(client.post("/api/chat", json={"message": case["message"]}))
            confirms = [e for e in evts if e["type"] == "confirm"]
            if confirms:
                approve = case.get("approve", True)
                decisions = {a["id"]: approve for a in confirms[0]["actions"]}
                body = {"thread_id": evts[0]["thread_id"], "decisions": decisions}
                evts += read_events(client.post("/api/chat/confirm", json=body))
            seconds = time.perf_counter() - start

    route = next((e["route"] for e in evts if e["type"] == "route"), "")
    calls = [e for e in evts if e["type"] == "tool_call"]
    outcomes = [e["outcome"] for e in evts if e["type"] == "tool_result"]
    answer = next((e for e in evts if e["type"] == "answer"), {})
    text = answer.get("text", "")
    error = next((e["message"] for e in evts if e["type"] == "error"), "")

    checks: dict[str, bool] = {"no_error": not error}
    if "route" in case:
        checks["route"] = route == case["route"]
    if "tool" in case:
        checks["tool"] = bool(calls) and calls[0]["name"] == case["tool"]
    if "args" in case:
        checks["args"] = bool(calls) and args_match(case["args"], calls[0]["args"])
    if "confirm" in case:
        checks["confirm"] = bool(confirms) == case["confirm"]
    if "outcome" in case:
        checks["outcome"] = case["outcome"] in outcomes
    if case.get("no_write"):
        writes = {name for name, action in ACTIONS.items() if action.writes}
        checks["no_write"] = not any(
            e["name"] in writes and e["outcome"] == "done" for e in evts if e["type"] == "tool_result"
        )
    if "no_tool" in case:
        checks["no_tool"] = all(c["name"] != case["no_tool"] for c in calls)
    if "contains" in case:
        checks["contains"] = all(s.lower() in text.lower() for s in case["contains"])
    if "not_contains" in case:
        checks["not_contains"] = not any(s.lower() in text.lower() for s in case["not_contains"])
    if "source" in case:
        checks["source"] = any(s["doc"] == case["source"] for s in answer.get("sources", []))
    return {
        "id": case["id"],
        "passed": all(checks.values()),
        "checks": checks,
        "seconds": round(seconds, 1),
        "route": route,
        "tools": [c["name"] for c in calls],
        "outcomes": outcomes,
        "answer": text or error,
    }


def rate(results: list[dict], check: str) -> str:
    relevant = [r["checks"][check] for r in results if check in r["checks"]]
    return (
        f"{sum(relevant)}/{len(relevant)} ({100 * sum(relevant) / len(relevant):.0f}%)" if relevant else "-"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--router", choices=["llm", "remote", "keywords"])
    parser.add_argument("--only", default="", help="run cases whose id starts with this")
    opts = parser.parse_args()

    settings = get_settings()
    cases = [json.loads(line) for line in (HERE / "cases.jsonl").read_text().splitlines() if line.strip()]
    cases = [c for c in cases if c["id"].startswith(opts.only)]
    embedder = FastEmbedder(settings.embed_model)

    results = []
    for case in cases:
        result = run_case(case, embedder, opts.router)
        results.append(result)
        failed = [k for k, v in result["checks"].items() if not v]
        mark = "PASS" if result["passed"] else f"FAIL {failed}"
        print(f"{result['seconds']:6.1f}s  {case['id']:20} {mark}", flush=True)

    safety = [r for r, c in zip(results, cases, strict=True) if c.get("safety")]
    summary = {
        "model": settings.llm_model,
        "base_url": settings.llm_base_url,
        "router": opts.router or settings.router_mode,
        "date": datetime.now(UTC).strftime("%Y-%m-%d"),
        "passed": f"{sum(r['passed'] for r in results)}/{len(results)}",
        "routing": rate(results, "route"),
        "tool_choice": rate(results, "tool"),
        "arguments": rate(results, "args"),
        "answers_contain_facts": rate(results, "contains"),
        "citations": rate(results, "source"),
        "safety_cases": f"{sum(r['passed'] for r in safety)}/{len(safety)}",
        "median_seconds": statistics.median(r["seconds"] for r in results) if results else 0,
    }
    print(json.dumps(summary, indent=2))
    out = HERE / "results"
    out.mkdir(exist_ok=True)
    name = f"{summary['date']}-{summary['router']}-{settings.llm_model.replace('/', '_')}.json"
    (out / name).write_text(
        json.dumps({"summary": summary, "results": results}, indent=2, ensure_ascii=False)
    )


if __name__ == "__main__":
    main()
