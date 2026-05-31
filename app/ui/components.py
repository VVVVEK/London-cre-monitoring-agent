"""Reusable Streamlit rendering components.

No business calculation belongs here. Components only render skill outputs.
"""
from __future__ import annotations

from typing import Any


SYNTHETIC_DISCLAIMER = (
    "Synthetic data is used only for PoC validation and alert/recommendation "
    "workflow testing. It is not a real market fact."
)


def render_quality_badge(st, quality: str) -> None:
    color = {
        "observed": "green",
        "estimated": "orange",
        "synthetic": "red",
        "mixed": "violet",
        "unknown": "gray",
    }.get(quality, "gray")
    st.markdown(f":{color}[**Data quality: {quality.upper()}**]")


def render_evidence_table(st, evidence: list[dict[str, Any]]) -> None:
    rows = []
    for ev in evidence:
        rows.append(
            {
                "metric": ev.get("metric", ""),
                "value": ev.get("value"),
                "source": ev.get("source", ""),
                "source_url": ev.get("source_url") or "",
                "timestamp": ev.get("timestamp", ""),
                "data_quality": ev.get("evidence_type", ""),
            }
        )
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("No evidence returned.")


def render_recommendation_result(st, result: dict[str, Any]) -> None:
    render_quality_badge(st, result.get("data_quality", "unknown"))
    st.metric("Confidence", result.get("confidence", 0.0))

    limitations = result.get("limitations") or ""
    if limitations:
        st.warning(limitations)
    if result.get("data_quality") in ("synthetic", "mixed") or "synthetic" in limitations.lower():
        st.error(SYNTHETIC_DISCLAIMER)

    st.subheader("Recommended Submarkets")
    for rec in result.get("recommended_submarkets", []):
        with st.container(border=True):
            st.markdown(f"### {rec['submarket']} — score {rec['score']}")
            render_quality_badge(st, rec.get("data_quality", "unknown"))
            st.write(rec.get("rationale", ""))
            render_evidence_table(st, rec.get("evidence", []))

    st.subheader("Recommended Actions")
    for action in result.get("recommended_actions", []):
        with st.container(border=True):
            st.markdown(f"**{action['priority']} priority:** {action['action']}")
            render_quality_badge(st, action.get("data_quality", "unknown"))
            st.write(action.get("rationale", ""))

    st.subheader("Data Provenance")
    render_evidence_table(st, result.get("evidence", []))
