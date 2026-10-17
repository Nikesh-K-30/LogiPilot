"""Dashboard copilot: Gemini when configured, deterministic fallback otherwise."""

from __future__ import annotations

import json
import re
from typing import Any

from app.config import get_settings
from app.schemas import ChatResponse
from app.services import routing
from app.services.negotiation import run_negotiation
from app.services.overview import build_overview


def parse_chat_intent(
    message: str,
    *,
    prioritize: str | None = None,
    allow_delay_hours: float | None = None,
) -> dict[str, Any]:
    """Derive optimization knobs from UI controls + natural-language message.

    Message text can override UI defaults when the user explicitly asks for
    carbon / utilization / delay hours.
    """
    msg = (message or "").lower()
    ui_priority = (prioritize or "cost").strip().lower()
    if ui_priority not in ("cost", "carbon", "utilization"):
        ui_priority = "cost"

    priority = ui_priority
    if any(k in msg for k in ("carbon", "emission", "co2", "co₂")):
        priority = "carbon"
    elif "utili" in msg and any(k in msg for k in ("priorit", "prefer", "optim")):
        priority = "utilization"
    elif re.search(r"\b(cheap|cheapest|cost|savings?|₹)\b", msg) and any(
        k in msg for k in ("priorit", "prefer", "optim", "find", "reduce")
    ):
        # Explicit cost wording wins back over a carbon UI default only when clear
        if "carbon" not in msg:
            priority = "cost"

    delay = float(allow_delay_hours) if allow_delay_hours is not None else 0.0
    hour_match = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:-?\s*)?(?:hour|hr|hrs)\b",
        msg,
    )
    if hour_match:
        delay = float(hour_match.group(1))
    elif any(k in msg for k in ("allow delay", "allow a delay", "with delay")) and delay <= 0:
        delay = 2.0

    is_what_if = any(
        k in msg
        for k in (
            "what if",
            "what-if",
            "reoptim",
            "re-optim",
            "scenario",
            "priorit",
            "carbon",
            "delay",
            "deadline",
        )
    )

    corridor: tuple[str, str] | None = None
    if any(k in msg for k in ("hyd", "hyderabad")) and any(
        k in msg for k in ("chennai", "maa", "madras")
    ):
        corridor = ("LOC-HYD", "LOC-MAA")

    unsupported: list[str] = []
    if "deadline" in msg or "19:00" in msg or "split" in msg or "half of" in msg:
        unsupported.append(
            "Per-shipment deadline edits and quantity splits are not applied from chat yet; "
            "ranking uses current SQLite deadlines. Priority/delay knobs below ARE applied."
        )

    return {
        "prioritize": priority,
        "allow_delay_hours": delay,
        "is_what_if": is_what_if or priority != "cost" or delay > 0,
        "corridor": list(corridor) if corridor else None,
        "unsupported_notes": unsupported,
        "ui_prioritize": ui_priority,
        "ui_allow_delay_hours": float(allow_delay_hours) if allow_delay_hours is not None else 0.0,
    }


def _slim_match(m: dict[str, Any] | None) -> dict[str, Any] | None:
    if not m:
        return None
    sav = m.get("consolidation_savings") or {}
    return {
        "match_id": m.get("match_id"),
        "vehicle_id": m.get("vehicle_id"),
        "shipment_ids": m.get("shipment_ids"),
        "shipper_names": m.get("shipper_names"),
        "incremental_distance_km": m.get("incremental_distance_km"),
        "savings_inr": sav.get("avoided_truck_savings"),
        "utilization_before_kg_pct": (m.get("capacity_utilization_before") or {}).get("kg"),
        "utilization_after_kg_pct": (m.get("capacity_utilization_after") or {}).get("kg"),
        "reasons": (m.get("reasons") or [])[:4],
    }


def _slim_recommendation(rec: dict[str, Any] | None) -> dict[str, Any] | None:
    if not rec:
        return None
    return {
        "match_id": rec.get("match_id"),
        "vehicle_id": rec.get("vehicle_id"),
        "shipment_ids": rec.get("shipment_ids"),
        "shippers": rec.get("shippers"),
        "savings_inr": rec.get("savings_inr"),
        "prioritize": rec.get("prioritize"),
        "utilization_before": rec.get("utilization_before"),
        "utilization_after": rec.get("utilization_after"),
        "explanation": rec.get("explanation"),
        "reasons": (rec.get("reasons") or [])[:4],
    }


def _filter_corridor(
    matches: list[dict[str, Any]],
    corridor: list[str] | None,
) -> list[dict[str, Any]]:
    if not corridor or len(corridor) != 2:
        return matches
    origin, dest = corridor[0], corridor[1]
    out: list[dict[str, Any]] = []
    for m in matches:
        # Prefer matches whose shipments touch the corridor when origin/dest present on match
        o = m.get("origin_id") or m.get("pickup_location_id")
        d = m.get("destination_id") or m.get("drop_location_id")
        if o and d:
            if o == origin and d == dest:
                out.append(m)
            continue
        # Fallback: keep if any shipment id is Hyd→Chennai open loads (heuristic via shipper/route labels)
        label = " ".join(
            str(x)
            for x in (
                m.get("shipper_names"),
                m.get("reasons"),
                m.get("shipment_ids"),
            )
        ).lower()
        if "hyd" in label or "chennai" in label or "maa" in label or "deccan" in label or "coastal" in label:
            out.append(m)
        else:
            out.append(m)  # keep all if we cannot filter safely; Gemini still sees intent.corridor
    return out or matches


def _keyword_chat(message: str, intent: dict[str, Any]) -> ChatResponse:
    settings = get_settings()
    msg = message.lower()
    findings: list[dict[str, Any]] = []
    prioritize = intent["prioritize"]
    delay = float(intent["allow_delay_hours"] or 0)

    if any(k in msg for k in ("why", "explain", "reason")) and not intent["is_what_if"]:
        neg = run_negotiation(prioritize=prioritize, allow_delay_hours=delay)
        rec = neg.get("recommendation") or {}
        answer = rec.get("explanation") or "No recommendation available yet. Add open loads or reset demo data."
        if rec:
            findings.append({"entity_id": rec.get("match_id"), "severity": "info", "reason": answer})
        return ChatResponse(
            answer=answer,
            findings=findings,
            source="negotiation",
            data_class=settings.data_class,
        )

    if intent["is_what_if"] or any(
        k in msg for k in ("what if", "what-if", "delay", "carbon", "prioritize", "reoptim")
    ):
        baseline = run_negotiation(prioritize="cost", allow_delay_hours=0.0)
        neg = run_negotiation(allow_delay_hours=delay, prioritize=prioritize)
        rec = neg.get("recommendation")
        base_rec = baseline.get("recommendation")
        notes = " ".join(intent.get("unsupported_notes") or [])
        if rec:
            changed = (
                (base_rec or {}).get("match_id") != rec.get("match_id")
                or (base_rec or {}).get("vehicle_id") != rec.get("vehicle_id")
                or list((base_rec or {}).get("shipment_ids") or [])
                != list(rec.get("shipment_ids") or [])
            )
            answer = (
                f"What-if (priority={prioritize}, allow_delay_hours={delay}): "
                f"best plan {rec.get('vehicle_id')} for {', '.join(rec.get('shipment_ids') or [])}. "
                f"Estimated savings ₹{float(rec.get('savings_inr') or 0):,.0f}. "
                f"{'Differs from cost baseline.' if changed else 'Same top plan as cost baseline (ranking tie / identical best).'} "
                f"{len(neg.get('feasible_matches') or [])} feasible options. {notes}"
            ).strip()
        else:
            answer = (
                f"What-if (priority={prioritize}, delay={delay}h): no feasible consolidations. {notes}"
            ).strip()
        return ChatResponse(
            answer=answer,
            findings=[{"entity_id": "what_if", "severity": "info", "reason": answer}],
            source="negotiation_what_if",
            data_class=settings.data_class,
        )

    if any(
        k in msg
        for k in (
            "cost",
            "save",
            "chennai",
            "reduce",
            "match",
            "pool",
            "spare",
            "capacity",
            "load",
            "truck",
            "consolidat",
            "opportun",
            "cheapest",
            "optim",
            "hyd",
        )
    ):
        neg = run_negotiation(prioritize=prioritize, allow_delay_hours=delay)
        summary = neg.get("opportunities_summary") or {}
        total = float(summary.get("total_avoided_truck_savings") or 0)
        feasible = neg.get("feasible_matches") or []
        combos = summary.get("shipper_combinations") or []
        answer = (
            f"LoadLink + Coordinator (priority={prioritize}): "
            f"{len(feasible)} consolidation option(s). "
            f"Estimated savings by avoiding second trucks: ₹{total:,.0f}. "
            f"Top: {', '.join(combos[:3]) or 'n/a'}. "
            "See Agent activity for the negotiation transcript. Figures are tool estimates."
        )
        for m in feasible[:5]:
            findings.append(
                {
                    "entity_id": ",".join(m.get("shipment_ids") or []),
                    "severity": "info",
                    "reason": "; ".join(m.get("reasons") or []),
                    "vehicle_id": m.get("vehicle_id"),
                    "savings": (m.get("consolidation_savings") or {}).get("avoided_truck_savings"),
                }
            )
        return ChatResponse(
            answer=answer,
            findings=findings,
            source="loadlink_matching",
            data_class=settings.data_class,
        )

    if any(k in msg for k in ("route", "optimize", "sequence", "fuel", "distance")):
        result = routing.optimize_route(
            depot_id="LOC-MUM", vehicle_id="VEH-001", route_id="RTE-100", mode="open"
        )
        answer = (
            f"RouteWise: baseline {result.baseline.distance_km} km → "
            f"optimized {result.optimized.distance_km} km "
            f"(save {result.savings.get('distance_km')} km). Feasible={result.feasible}."
        )
        return ChatResponse(
            answer=answer,
            findings=[{"entity_id": result.run_id, "severity": "info", "reason": answer}],
            source="routewise_routing",
            data_class=settings.data_class,
        )

    return ChatResponse(
        answer=(
            "Try: “Find the cheapest way to deliver today's Chennai shipments”, "
            "“Why this plan?”, “What if I allow a 2-hour delay?”, or “Prioritize carbon”. "
            "Or add a new load from the form — NEW_SHIPMENT will re-run matching."
        ),
        findings=[],
        source="api",
        data_class=settings.data_class,
    )


def _build_tool_context(intent: dict[str, Any]) -> dict[str, Any]:
    prioritize = intent["prioritize"]
    delay = float(intent["allow_delay_hours"] or 0)
    overview = build_overview(advance_fleet=False)

    scenario = run_negotiation(prioritize=prioritize, allow_delay_hours=delay)
    baseline = None
    if intent.get("is_what_if") or prioritize != "cost" or delay > 0:
        baseline = run_negotiation(prioritize="cost", allow_delay_hours=0.0)

    feasible = scenario.get("feasible_matches") or []
    if intent.get("corridor"):
        feasible = _filter_corridor(feasible, intent["corridor"])

    unassigned = overview.get("unassigned_shipments") or []
    if intent.get("corridor"):
        o, d = intent["corridor"][0], intent["corridor"][1]
        filtered = [
            s
            for s in unassigned
            if s.get("origin_id") == o and s.get("destination_id") == d
        ]
        if filtered:
            unassigned = filtered

    context: dict[str, Any] = {
        "intent": intent,
        "kpis": overview.get("kpis"),
        "unassigned_open_loads": [
            {
                "shipment_id": s.get("shipment_id"),
                "shipper_name": s.get("shipper_name"),
                "origin_id": s.get("origin_id"),
                "destination_id": s.get("destination_id"),
                "weight_kg": s.get("weight_kg"),
                "cargo_class": s.get("cargo_class"),
                "deadline": s.get("deadline"),
            }
            for s in unassigned[:10]
        ],
        "fleet_now": [
            {
                "vehicle_id": v["vehicle_id"],
                "utilization_pct_now": v["utilization_pct"],
                "remaining_kg": v["remaining_kg"],
                "route_label": v.get("route_label"),
                "availability": v["availability"],
            }
            for v in (overview.get("fleet") or {}).get("vehicles", [])
        ],
        "scenario": {
            "prioritize": scenario.get("prioritize"),
            "allow_delay_hours": scenario.get("allow_delay_hours"),
            "recommendation": _slim_recommendation(scenario.get("recommendation")),
            "top_matches": [_slim_match(m) for m in feasible[:5]],
            "rejected_preview": (scenario.get("rejected") or [])[:4],
            "recent_activity": (scenario.get("activity") or [])[-6:],
        },
    }
    if baseline is not None:
        context["baseline_cost"] = {
            "recommendation": _slim_recommendation(baseline.get("recommendation")),
            "top_match_id": (baseline.get("recommendation") or {}).get("match_id"),
        }
        scen_id = (scenario.get("recommendation") or {}).get("match_id")
        base_id = (baseline.get("recommendation") or {}).get("match_id")
        context["scenario_vs_baseline"] = {
            "changed": scen_id != base_id,
            "baseline_match_id": base_id,
            "scenario_match_id": scen_id,
        }
    return context


def _gemini_chat(message: str, intent: dict[str, Any]) -> ChatResponse | None:
    settings = get_settings()
    if not settings.google_api_key:
        return None
    try:
        from google import genai
    except ImportError:
        return None

    context = _build_tool_context(intent)
    prompt = f"""You are the FreightMesh / LogiPilot Logistics Manager speaking to a dispatcher.

CRITICAL RULES:
- Use ONLY the JSON context (tool results). Never invent shipment IDs, ₹ amounts, or utilization %.
- Answer the USER's question directly. Do NOT tell them to use "What-if controls" or other UI buttons.
- intent.prioritize and scenario already reflect their ask (and UI knobs). Explain THAT scenario.
- If scenario_vs_baseline.changed is false, say the top plan is unchanged under this priority — then highlight what still differs (e.g. ranking rationale, incremental km).
- If scenario_vs_baseline.changed is true, contrast baseline_cost vs scenario recommendations.
- fleet_now.utilization_pct_now is CURRENT fill. utilization_after on a match is PROJECTED after loading — do not confuse them.
- If intent.unsupported_notes is non-empty, mention those limits briefly (deadline/split edits).
- Prefer Markdown: short heading, bullets. Pick top 1–2 plans, not a wall of equal options.
- If intent.corridor is set, focus on that origin→destination.

Context:
{json.dumps(context, default=str)[:14000]}

User: {message}
"""
    try:
        from google.genai import types as genai_types

        client = genai.Client(api_key=settings.google_api_key)
        model = settings.gemini_model or "gemini-flash-latest"
        resp = client.models.generate_content(
            model=model,
            contents=prompt,
            config=genai_types.GenerateContentConfig(temperature=0.2),
        )
        text = (resp.text or "").strip()
        if not text:
            return None
        return ChatResponse(
            answer=text,
            findings=[
                {
                    "entity_id": "gemini",
                    "severity": "info",
                    "reason": (
                        f"Grounded on tools · priority={intent['prioritize']} · "
                        f"delay={intent['allow_delay_hours']}h"
                    ),
                }
            ],
            source="gemini_manager",
            data_class=settings.data_class,
        )
    except Exception:
        # Invalid key / quota / model / config — caller falls back to deterministic Manager
        return None


def handle_chat(
    message: str,
    *,
    prioritize: str | None = None,
    allow_delay_hours: float | None = None,
) -> ChatResponse:
    intent = parse_chat_intent(
        message,
        prioritize=prioritize,
        allow_delay_hours=allow_delay_hours,
    )
    gem = _gemini_chat(message, intent)
    if gem is not None:
        return gem
    return _keyword_chat(message, intent)
