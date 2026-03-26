"""Streamlit Chat UI for the LLM-in-the-middle Pipeline (Phase 2 POC).

Features:
- Chat interface for asking questions
- Displays SQL, results table, and explanation
- Shows pipeline metadata (latency, tokens, attempts)
"""

import streamlit as st
import httpx

API_URL = "http://localhost:8000"

st.set_page_config(
    page_title="Text-to-SQL Pipeline",
    page_icon="🏦",
    layout="wide",
)

st.title("Text-to-SQL Pipeline — Banking/POS")
st.caption("LLM-in-the-middle Pipeline (Phase 2 POC)")

# Session state
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "sql" in msg:
            st.code(msg["sql"], language="sql")
        if "data" in msg:
            st.dataframe(msg["data"], use_container_width=True)
        if "metadata" in msg:
            cols = st.columns(4)
            meta = msg["metadata"]
            cols[0].metric("Latency", f"{meta.get('latency_ms', 0)}ms")
            cols[1].metric("Tokens", meta.get("total_tokens", 0))
            cols[2].metric("Attempts", meta.get("attempts", 1))
            cols[3].metric("Intent", meta.get("intent", "sql"))

# Chat input
if question := st.chat_input("Hỏi về dữ liệu Banking/POS..."):
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Đang xử lý..."):
            try:
                response = httpx.post(
                    f"{API_URL}/api/query",
                    json={"question": question},
                    timeout=60.0,
                )
                data = response.json()

                msg: dict = {"role": "assistant", "content": ""}

                if data.get("status") == "success":
                    if data.get("sql"):
                        st.code(data["sql"], language="sql")
                        msg["sql"] = data["sql"]

                    results = data.get("results")
                    if results and results.get("rows"):
                        import pandas as pd
                        df = pd.DataFrame(results["rows"], columns=results["columns"])
                        st.dataframe(df, use_container_width=True)
                        msg["data"] = df.to_dict()
                        msg["content"] = f"Trả về {results['row_count']} dòng kết quả."
                    else:
                        msg["content"] = "Truy vấn thành công nhưng không có kết quả."

                else:
                    explanation = data.get("explanation", "")
                    st.markdown(explanation)
                    msg["content"] = explanation

                # Show metadata
                metadata = data.get("metadata", {})
                if metadata:
                    cols = st.columns(4)
                    cols[0].metric("Latency", f"{metadata.get('latency_ms', 0)}ms")
                    cols[1].metric("Tokens", metadata.get("total_tokens", 0))
                    cols[2].metric("Attempts", metadata.get("attempts", 1))
                    cols[3].metric("Intent", metadata.get("intent", "sql"))
                    msg["metadata"] = metadata

                st.session_state.messages.append(msg)

            except httpx.ConnectError:
                st.error("Không thể kết nối API server. Hãy đảm bảo server đang chạy (uvicorn src.api.app:app).")
            except Exception as e:
                st.error(f"Lỗi: {e}")
