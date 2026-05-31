"""Streamlit entrypoint for the London CRE AI Agent."""
from __future__ import annotations

from app.orchestrator import orchestrator
from app.ui.components import render_recommendation_result


def _recommendation_dialog(st) -> None:
    dialog = getattr(st, "dialog", None) or getattr(st, "experimental_dialog", None)

    def body() -> None:
        st.write("Generate an evidence-backed recommendation. Business logic is executed by recommendation_skill.")
        goal = st.selectbox("User goal", ["Risk-Averse", "Return-Seeking", "Balanced"], index=2)
        risk_level = st.selectbox("Risk level", ["Low", "Medium", "High"], index=1)
        horizon_months = st.selectbox("Time horizon", [3, 6, 12], index=1)
        preferred_submarkets = st.multiselect(
            "Submarket preference",
            ["City", "West End", "Canary Wharf", "Midtown"],
            default=[],
        )
        budget = st.number_input("Optional budget (GBP mn)", min_value=0.0, value=0.0, step=5.0)
        allow_synthetic = st.checkbox("Allow synthetic PoC data", value=True)

        if st.button("Generate Recommendation", type="primary"):
            result = orchestrator.recommend(
                goal=goal,
                risk_level=risk_level,
                horizon_months=horizon_months,
                preferred_submarkets=preferred_submarkets,
                budget_million_gbp=budget if budget > 0 else None,
                allow_synthetic=allow_synthetic,
            )
            st.session_state["recommendation_result"] = result
            render_recommendation_result(st, result)

    if dialog:
        dialog("Recommendation")(body)()
    else:
        st.subheader("Recommendation")
        body()


def main() -> None:
    """Streamlit application entrypoint."""
    try:
        import streamlit as st
    except ImportError as exc:  # pragma: no cover - runtime dependency check
        raise RuntimeError("Streamlit is not installed. Run `pip install -r requirements.txt`.") from exc

    st.set_page_config(page_title="London CRE AI Agent", layout="wide")
    st.title("London Office CRE Monitoring AI Agent")
    st.caption("CLI remains the primary deterministic path; this UI calls the same orchestrator/skills.")

    col1, col2, col3 = st.columns(3)
    if col1.button("Run Pipeline"):
        st.session_state["pipeline_result"] = orchestrator.run_pipeline()
    if col2.button("Open Recommendation", type="primary"):
        st.session_state["show_recommendation_dialog"] = True
    if col3.button("Generate Weekly Report"):
        st.session_state["report_result"] = orchestrator.run_weekly_briefing()

    if "pipeline_result" in st.session_state:
        st.subheader("Pipeline Result")
        st.json(st.session_state["pipeline_result"])

    if "report_result" in st.session_state:
        st.subheader("Report Result")
        st.json(st.session_state["report_result"].get("report", {}))

    if st.session_state.get("show_recommendation_dialog"):
        _recommendation_dialog(st)

    if "recommendation_result" in st.session_state:
        st.subheader("Latest Recommendation")
        render_recommendation_result(st, st.session_state["recommendation_result"])


if __name__ == "__main__":
    main()
