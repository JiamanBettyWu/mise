"""Export a Weave trip_planner trace as replay JSON for the site's <PipelineReplay />.

Usage:
    .venv/bin/python scripts/export_replay_trace.py <weave-call-id> [out.json]

Reads one recorded plan_trip call from Weave, flattens the LangGraph node spans
into a timeline, attaches a short human-readable summary per node (this is also
the redaction layer: only what's written here ships publicly), and writes the
JSON the React component consumes.
"""

import json
import sys

import weave
from dotenv import load_dotenv

load_dotenv("../.env")

GRAPH = {
    "nodes": [
        "get_weather",
        "infer_weather_if_needed",
        "get_catalog",
        "reason_and_select",
        "plan_purchase_queries",
        "search_purchases",
        "generate_output",
    ],
    "edges": [
        ["__start__", "get_weather"],
        ["__start__", "get_catalog"],
        ["get_weather", "infer_weather_if_needed"],
        ["infer_weather_if_needed", "reason_and_select"],
        ["get_catalog", "reason_and_select"],
        ["reason_and_select", "generate_output"],
        ["generate_output", "plan_purchase_queries"],
        ["generate_output", "__end__"],
        ["plan_purchase_queries", "search_purchases"],
        ["search_purchases", "__end__"],
    ],
    # check_gaps routes generate_output -> plan_purchase_queries (has_gaps) or END
    "conditional_edges": [
        ["generate_output", "plan_purchase_queries"],
        ["generate_output", "__end__"],
    ],
}


def out_of(call):
    o = call.output
    return o.get("outputs", {}) if isinstance(o, dict) else {}


def summarize(name: str, outputs: dict) -> str:
    """One public-safe line per node. Anything not stated here never leaves Weave."""
    if name == "get_weather":
        return "Asked OpenWeatherMap for the trip dates — too far out, no forecast available."
    if name == "infer_weather_if_needed":
        return "Fallback: asked the LLM for typical Paris mid-July climate (warm-to-hot days, mild evenings, occasional showers)."
    if name == "get_catalog":
        n = len(outputs.get("catalog", []))
        return f"Pulled the full available wardrobe from the database: {n} items."
    if name == "reason_and_select":
        c = len(outputs.get("candidate_items", []))
        g = len(outputs.get("gaps", []))
        return f"LLM reasoned over wardrobe × climate: picked {c} items and flagged {g} gaps the closet can't cover."
    if name == "plan_purchase_queries":
        return "Turned each gap into a shopping search query, steered by stated + inferred style preferences."
    if name == "search_purchases":
        n = len(outputs.get("purchase_suggestions", []))
        return f"Ran the queries against SerpAPI (Google Shopping), concurrently: {n} concrete product suggestions."
    if name == "generate_output":
        n = len(outputs.get("packing_list", []))
        return f"Assembled the final packing list ({n} categories) plus the buy-list."
    return ""


def main() -> None:
    call_id = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else "replay-trace.json"

    client = weave.init("wardrobe-ai")
    root = client.get_call(call_id)
    graph_call = next(iter(root.children()))
    t0 = graph_call.started_at

    events = []
    for c in graph_call.children():
        name = c.op_name.split("/")[-1].split(":")[0].removeprefix("langchain.Chain.")
        llm_ms = None
        for ch in c.children():
            if "anthropic" in ch.op_name:
                llm_ms = round((ch.ended_at - ch.started_at).total_seconds() * 1000)
        events.append(
            {
                "node": name,
                "start_ms": round((c.started_at - t0).total_seconds() * 1000),
                "end_ms": round((c.ended_at - t0).total_seconds() * 1000),
                "llm_ms": llm_ms,
                "summary": summarize(name, out_of(c)),
            }
        )

    trace = {
        "title": "Trip: Paris, 5 days in mid-July",
        "total_ms": round((graph_call.ended_at - t0).total_seconds() * 1000),
        "graph": GRAPH,
        "events": events,
    }
    with open(out_path, "w") as f:
        json.dump(trace, f, indent=2)
    print(f"wrote {out_path}: {len(events)} events, {trace['total_ms']} ms total")


if __name__ == "__main__":
    main()
