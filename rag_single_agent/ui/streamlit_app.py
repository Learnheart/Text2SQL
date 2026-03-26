"""Streamlit Chat UI for Text-to-SQL Agent (POC)."""

import streamlit as st
import httpx

API_BASE = "http://localhost:8000"

st.set_page_config(page_title="Text-to-SQL Agent", page_icon="🔍", layout="wide")
st.title("Text-to-SQL Agent — Banking/POS")

# Sidebar
with st.sidebar:
    st.header("Quick Questions")
    suggestions = [
        "Tổng doanh thu tháng này?",
        "Top 5 merchant doanh thu cao nhất?",
        "How many failed transactions this week?",
        "Phân bố KYC status của khách hàng?",
        "Revenue by product category?",
    ]
    for s in suggestions:
        if st.button(s, key=s):
            st.session_state["input_question"] = s

    st.divider()
    st.caption("Phase 1 (R&D) — RAG-Enhanced Single Agent")

# Chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "sql" in msg:
            st.code(msg["sql"], language="sql")
        if "data" in msg:
            st.dataframe(msg["data"])

# Input
prompt = st.chat_input("Ask a question about Banking/POS data...")
if "input_question" in st.session_state:
    prompt = st.session_state.pop("input_question")

if prompt:
    # Show user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Call API
    with st.chat_message("assistant"):
        with st.spinner("Querying..."):
            try:
                resp = httpx.post(
                    f"{API_BASE}/api/query",
                    json={"question": prompt},
                    timeout=90.0,
                )
                result = resp.json()

                msg = {"role": "assistant", "content": result.get("explanation", "")}

                # Show SQL
                if result.get("sql"):
                    st.code(result["sql"], language="sql")
                    msg["sql"] = result["sql"]

                # Show results
                if result.get("results") and result["results"].get("rows"):
                    import pandas as pd

                    df = pd.DataFrame(
                        result["results"]["rows"],
                        columns=result["results"].get("columns", []),
                    )
                    st.dataframe(df)
                    msg["data"] = df.to_dict()

                # Show explanation
                st.markdown(result.get("explanation", ""))

                # Show metadata
                meta = result.get("metadata", {})
                if meta:
                    st.caption(
                        f"⏱ {meta.get('latency_ms', 0)}ms | "
                        f"🔧 {meta.get('tool_calls', 0)} tool calls | "
                        f"📊 {meta.get('tokens', 0)} tokens"
                    )

                st.session_state.messages.append(msg)

            except Exception as e:
                st.error(f"Error: {e}")
                st.session_state.messages.append(
                    {"role": "assistant", "content": f"Error: {e}"}
                )
