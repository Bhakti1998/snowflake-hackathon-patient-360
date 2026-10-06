"""Snowflake-hosted four-screen evidence application. No embedded credentials."""

import uuid
import re

import _snowflake
import streamlit as st
from snowflake.snowpark.context import get_active_session
from snowflake.snowpark.exceptions import SnowparkClientException
from response import parse_response, validate_format, SCOPE_REFUSAL

DB = "CARELENS360_MVP"
session = get_active_session()
st.set_page_config(page_title="CareLens360", layout="wide")
st.title("CareLens360")
st.warning("Synthetic data only. The risk score is a demonstration rule, not a validated clinical model.")
st.caption("An Incomplete tier reports a partial point sum with unknown inputs, not a finalized risk score.")


def query(sql, params=None):
    return session.sql(sql, params=params or []).to_pandas()


def audit(plan, operation, status):
    session.sql(f"""INSERT INTO {DB}.APP.ACCESS_AUDIT
      (REQUEST_ID,USER_NAME,PLAN_ID,OPERATION,STATUS)
      SELECT ?,CURRENT_USER(),?,?,?""", params=[str(uuid.uuid4()), plan, operation, status]).collect()


plans = query(f"""SELECT DISTINCT m.PLAN_ID FROM {DB}.APP.MEMBER_360_SNAPSHOT m ORDER BY PLAN_ID""")
if plans.empty:
    st.error("No authorized member/plan entitlement was found. Contact the project administrator.")
    st.stop()
plan = st.sidebar.selectbox("Authorized plan", plans["PLAN_ID"].tolist())
members = query(f"SELECT * FROM {DB}.APP.MEMBER_360_SNAPSHOT WHERE PLAN_ID=? ORDER BY PATIENT_ID", [plan])
screen = st.sidebar.radio("Screen", ["Member Search", "Member 360", "Evidence Copilot", "Population Insights"])
selected = st.sidebar.selectbox("Member", members["PATIENT_ID"].tolist())
mid = members.loc[members["PATIENT_ID"] == selected, "MEMBER_ID"].iloc[0]
state = query(f"SELECT SOURCE_VERSION,PIPELINE_STATUS FROM {DB}.APP.WORKFLOW_STATE").iloc[0]
if state["PIPELINE_STATUS"] != "SUCCEEDED":
    st.error("Refresh is running, failed or not yet verified. Review the pipeline audit before using this snapshot.")
    st.stop()
context = (plan, selected, str(state["SOURCE_VERSION"]))
if st.session_state.get("context") != context:
    st.session_state.pop("answer", None)
    pending = query(f"""SELECT DOCUMENT_ID,STATUS FROM {DB}.APP.DOCUMENT_STATUS
      WHERE STATUS!='READY' AND (PATIENT_ID=? OR PLAN_ID='SHARED')""", [selected])
    if not pending.empty:
        raise RuntimeError("Required document processing is pending or failed; review parse/audit records.")
    st.session_state.pop("messages", None)
    st.session_state["context"] = context

try:
    if screen == "Member Search":
        risk = st.selectbox("Risk tier", ["All"] + sorted(members["RISK_TIER"].unique()))
        condition = st.text_input("Condition key (e.g. T2D, HTN, CKD3, ASTHMA, HF)")
        shown = members if risk == "All" else members[members["RISK_TIER"] == risk]
        if condition:
            eligible = query(f"""SELECT MEMBER_ID FROM {DB}.APP.FACT_DIAGNOSIS
              WHERE CONDITION_KEY=? AND STATUS='active'""", [condition.upper()])
            shown = shown[shown["MEMBER_ID"].isin(eligible["MEMBER_ID"])]
        st.metric("Members matching filters", len(shown))
        st.dataframe(shown, hide_index=True)
        st.bar_chart(shown["RISK_TIER"].value_counts())
    elif screen == "Member 360":
        st.dataframe(members[members["MEMBER_ID"] == mid], hide_index=True)
        for title, source in [("Diagnoses", "FACT_DIAGNOSIS"), ("Medication adherence", "FACT_MEDICATION"),
                              ("Encounters", "FACT_ENCOUNTER"), ("Labs", "FACT_LAB_RESULT"),
                              ("Claims", "FACT_CLAIM"), ("Care gaps", "CARE_GAPS"),
                              ("Risk contributions", "MEMBER_RISK_FACTORS")]:
            st.subheader(title)
            st.dataframe(query(f"SELECT * FROM {DB}.APP.{source} WHERE MEMBER_ID=?", [mid]), hide_index=True)
        audit(plan, "MEMBER_360", "SUCCEEDED")
    elif screen == "Population Insights":
        st.metric("High + Critical members", int(members["RISK_TIER"].isin(["High", "Critical"]).sum()))
        st.bar_chart(members["RISK_TIER"].value_counts())
        condition_risk = query(f"""SELECT d.CONDITION_KEY,m.RISK_TIER,COUNT(DISTINCT m.MEMBER_ID) MEMBERS
          FROM {DB}.APP.MEMBER_360_SNAPSHOT m JOIN {DB}.APP.FACT_DIAGNOSIS d USING(MEMBER_ID)
          WHERE m.PLAN_ID=? GROUP BY d.CONDITION_KEY,m.RISK_TIER""", [plan])
        st.subheader("Risk by condition")
        st.dataframe(condition_risk, hide_index=True)
        st.subheader("Utilization, adherence and care gaps")
        st.dataframe(members[["PATIENT_ID", "ED_COUNT", "ADHERENCE", "CARE_GAP_COUNT", "FOLLOW_UP_GAP_COUNT"]])
        audit(plan, "POPULATION", "SUCCEEDED")
    else:
        question = st.text_input("Evidence question", value=f"Summarize member {selected}.")
        if st.button("Ask Cortex Agent", disabled=not question.strip()):
            st.session_state.pop("answer", None)
            tag = plan.replace("-", "_")
            # The literal plan agent has a hard server-side source boundary.
            if tag not in {"PLAN_1", "PLAN_2", "PLAN_3", "PLAN_4"}:
                raise ValueError("Unsupported plan")
            body = {"stream": False, "messages": st.session_state.get("messages", [])[-10:] + [{"role": "user", "content": [{"type": "text", "text":
                f"Selected patient {selected}, member {mid}, plan {plan}. "
                "As-of 2026-09-30. " + question}]}]}
            with st.spinner("Retrieving governed evidence (this can take a few minutes)..."):
                # Must exceed the agent's 300s orchestration budget so the reply is never cut off.
                response = _snowflake.send_snow_api_request(
                    "POST", f"/api/v2/databases/{DB}/schemas/APP/agents/CARE_LENS_AGENT_{tag}:run",
                    {}, {}, body, None, 360000)
            if int(response["status"]) >= 400:
                audit(plan, "AGENT", "FAILED")
                raise RuntimeError(f"Cortex Agent returned HTTP {response['status']}; no answer was accepted.")
            parsed = parse_response(response["content"])
            parsed["text"] = validate_format(parsed["text"])
            citations = []
            for annotation in parsed["annotations"]:
                if annotation.get("type") != "cortex_search_citation":
                    continue
                resolved = query(f"""SELECT CHUNK_ID,DOCUMENT_ID,DOCUMENT_DATE,PAGE_NUMBER,SECTION,
                  SOURCE_FILE,CHUNK_TEXT,SOURCE_SYSTEM,AUTHOR_ROLE,SHA256
                  FROM {DB}.APP.DOCUMENT_CHUNKS WHERE CHUNK_ID=?
                    AND (PLAN_ID=? OR PLAN_ID='SHARED')
                    AND (PATIENT_ID=? OR PATIENT_ID IS NULL OR PATIENT_ID='None')""",
                                 [annotation["doc_id"], plan, selected])
                if len(resolved) != 1:
                    raise RuntimeError("Citation failed source/member/plan verification; answer withheld")
                normalize = lambda s: re.sub(r"\s+", " ", s).strip()
                quote = annotation.get("text", "")
                if quote and normalize(quote) not in normalize(resolved.iloc[0]["CHUNK_TEXT"]):
                    raise RuntimeError("Citation snippet is not supported by its source chunk")
                citations.append(resolved.iloc[0].to_dict())
            scope_summary = re.search(r"^## Summary\s*\n(.*?)\n## Key Evidence",
                                      parsed["text"], re.DOTALL | re.MULTILINE)
            scope_refusal = scope_summary is not None and scope_summary.group(1).strip() == SCOPE_REFUSAL
            safe_fallback = ("I could not find sufficient evidence in the synthetic records."
                             in parsed["text"] or scope_refusal)
            search_used = any(r.get("type") == "cortex_search" or
                              r.get("name") in {"ClinicalDocumentSearch", "SharedEvidenceSearch"}
                              for r in parsed["tool_results"])
            if search_used and not citations and not safe_fallback:
                raise RuntimeError("Document-tool answer has no verifiable source citations; answer withheld")
            if not safe_fallback and not parsed["tool_results"]:
                raise RuntimeError("No actual tool evidence was returned; answer withheld")
            st.session_state["answer"] = {"text": parsed["text"],
                                         "sources": parsed["tool_results"], "citations": citations,
                                         "tool_warnings": parsed.get("tool_warnings", [])}
            st.session_state["messages"] = body["messages"] + [
                {"role": "assistant", "content": [{"type": "text", "text": parsed["text"]}]}]
            audit(plan, "AGENT", "SUCCEEDED")
        if "answer" in st.session_state:
            answer_text = st.session_state["answer"]["text"]
            for tw in st.session_state["answer"].get("tool_warnings", []):
                st.warning(f"Partial evidence: {tw}. The answer below may be incomplete.")
            if any(kw in answer_text.lower() for kw in ["conflicting", "conflict", "contradicts", "disagree"]):
                st.warning("Conflicting evidence detected. Review the cited sources below for discrepancies.")
            if "I could not find sufficient evidence" in answer_text:
                st.info("Insufficient evidence. The response below is based on incomplete data.")
            st.markdown(answer_text)
            st.caption("Source traceability checks do not replace claim-level semantic support review.")
            st.dataframe(st.session_state["answer"]["citations"])
            with st.expander("Evidence/tool inputs (not hidden reasoning)"):
                st.json(st.session_state["answer"]["sources"])
except (SnowparkClientException, RuntimeError, ValueError, KeyError, TypeError) as exc:
    # Do not turn a connection/model/policy error into an empty clinical answer.
    st.session_state.pop("answer", None)
    st.error(f"Operation failed: {exc}")
    audit(plan, screen, "FAILED")
    st.stop()
