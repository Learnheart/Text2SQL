"""Router [CODE] — Deterministic intent classification using keyword matching and regex.

Classifies user questions into 4 intents:
- SQL: Data query that should go through the pipeline
- Chitchat: Greetings, thanks, small talk
- Clarification: Domain-related but too vague
- Out-of-scope: Completely unrelated to Banking/POS

No LLM is used — this is pure keyword matching and regex.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from src.models.schemas import IntentType, RouterResult
from src.pipeline.state import PipelineState

if TYPE_CHECKING:
    from src.session_logger import SessionLogger

# --- Keyword sets ---

SQL_KEYWORDS: set[str] = {
    # Vietnamese query words
    "bao nhiêu", "tổng", "trung bình", "so sánh", "top", "doanh thu",
    "lợi nhuận", "số lượng", "đếm", "cao nhất", "thấp nhất", "nhiều nhất",
    "ít nhất", "tỷ lệ", "phần trăm", "tăng", "giảm", "thống kê",
    "báo cáo", "danh sách", "liệt kê", "chi tiết", "tìm",
    "trung vị", "tổng hợp", "phân tích", "xếp hạng",
    # English query words
    "how many", "total", "average", "compare", "top", "revenue",
    "count", "highest", "lowest", "most", "least", "rate", "percent",
    "increase", "decrease", "statistics", "report", "list", "find",
    "sum", "max", "min", "group by", "order by",
    # Specific question patterns
    "là bao nhiêu", "bằng bao nhiêu", "có bao nhiêu",
    "which", "what is", "show me", "give me", "calculate",
}

CHITCHAT_KEYWORDS: set[str] = {
    # Vietnamese
    "xin chào", "chào bạn", "chào", "cảm ơn", "cám ơn", "tạm biệt",
    "bạn là ai", "bạn tên gì", "bạn có thể", "giúp tôi", "hello",
    "bạn khỏe không", "chào buổi sáng", "chào buổi tối",
    # English
    "hi", "hello", "hey", "thanks", "thank you", "bye", "goodbye",
    "who are you", "what are you", "help me", "good morning", "good evening",
}

DOMAIN_KEYWORDS: set[str] = {
    # Vietnamese
    "giao dịch", "merchant", "pos", "ngân hàng", "thẻ", "tài khoản",
    "khách hàng", "chi nhánh", "nhân viên", "chuyển khoản", "hoàn tiền",
    "sản phẩm", "terminal", "doanh số", "sao kê",
    # English
    "transaction", "merchant", "pos", "bank", "card", "account",
    "customer", "branch", "employee", "transfer", "refund",
    "product", "terminal", "sales", "statement",
}

# --- Regex patterns ---

SQL_PATTERNS: list[re.Pattern] = [
    re.compile(r"(tháng|quý|năm|tuần)\s*\d+", re.IGNORECASE),
    re.compile(r"(month|quarter|year|week)\s*\d+", re.IGNORECASE),
    re.compile(r"(q[1-4]|h[12])\b", re.IGNORECASE),
    re.compile(r"(từ|from)\s+.*(đến|to)\s+", re.IGNORECASE),
    re.compile(r"\d{4}[-/]\d{1,2}", re.IGNORECASE),  # date patterns
    re.compile(r"(last|previous|next|this)\s+(month|week|year|quarter)", re.IGNORECASE),
    re.compile(r"(số liệu|thống kê|báo cáo)", re.IGNORECASE),
    re.compile(r"(distribution|breakdown|trend|growth)", re.IGNORECASE),
]


def route(state: PipelineState, *, session_log: SessionLogger | None = None) -> PipelineState:
    """Classify intent and return updated state with RouterResult.

    Processing time target: ~30ms.
    """
    question = state["question"].strip()
    q_lower = question.lower()

    if session_log:
        session_log.step(1, "ROUTER", f"Classifying intent for: {question[:80]}")

    # 1. Check chitchat first (short, greeting-like messages)
    if _is_chitchat(q_lower):
        result = RouterResult(
            intent=IntentType.CHITCHAT,
            confidence=0.95,
            message=_chitchat_response(q_lower),
        )
        if session_log:
            session_log.detail("ROUTER", f"Intent: CHITCHAT (confidence={result.confidence})")
        return {**state, "router_result": result, "status": "rejected"}

    # 2. Check SQL keywords
    sql_score = _sql_keyword_score(q_lower)
    if sql_score >= 0.5:
        result = RouterResult(intent=IntentType.SQL, confidence=min(0.95, 0.5 + sql_score))
        if session_log:
            session_log.detail("ROUTER", f"Intent: SQL (confidence={result.confidence:.2f}, score={sql_score:.2f})")
        return {**state, "router_result": result}

    # 3. Check regex patterns
    if _matches_sql_pattern(q_lower):
        result = RouterResult(intent=IntentType.SQL, confidence=0.80)
        if session_log:
            session_log.detail("ROUTER", "Intent: SQL via regex pattern (confidence=0.80)")
        return {**state, "router_result": result}

    # 4. Check domain keywords (might need clarification)
    if _has_domain_keyword(q_lower):
        if len(question.split()) <= 2:
            # Too short/vague — ask for clarification
            result = RouterResult(
                intent=IntentType.CLARIFICATION,
                confidence=0.70,
                message=_clarification_response(question),
            )
            if session_log:
                session_log.detail("ROUTER", "Intent: CLARIFICATION (too vague)")
        else:
            # Has domain keyword + enough context → treat as SQL
            result = RouterResult(intent=IntentType.SQL, confidence=0.70)
            if session_log:
                session_log.detail("ROUTER", "Intent: SQL via domain keyword (confidence=0.70)")
        return {**state, "router_result": result}

    # 5. Out of scope
    result = RouterResult(
        intent=IntentType.OUT_OF_SCOPE,
        confidence=0.85,
        message=_out_of_scope_response(),
    )
    if session_log:
        session_log.detail("ROUTER", "Intent: OUT_OF_SCOPE")
    return {**state, "router_result": result, "status": "rejected"}


# --- Private helpers ---


def _is_chitchat(q_lower: str) -> bool:
    words = set(q_lower.split())
    for keyword in CHITCHAT_KEYWORDS:
        if " " in keyword:
            # Multi-word: substring match is fine
            if keyword in q_lower:
                return True
        else:
            # Single-word: require whole-word match to avoid false positives
            # e.g., "hi" should not match "bao nhiêu" or "chi nhánh"
            if keyword in words:
                return True
    # Very short messages without domain content
    if len(words) <= 2 and not _has_domain_keyword(q_lower):
        for keyword in {"hi", "hey", "ok", "yes", "no", "có", "không", "ừ", "ờ"}:
            if q_lower.strip() == keyword:
                return True
    return False


def _sql_keyword_score(q_lower: str) -> float:
    matches = sum(1 for kw in SQL_KEYWORDS if kw in q_lower)
    return min(1.0, matches * 0.3)


def _matches_sql_pattern(q_lower: str) -> bool:
    return any(p.search(q_lower) for p in SQL_PATTERNS)


def _has_domain_keyword(q_lower: str) -> bool:
    return any(kw in q_lower for kw in DOMAIN_KEYWORDS)


def _chitchat_response(q_lower: str) -> str:
    if any(w in q_lower for w in ("chào", "hello", "hi", "hey")):
        return (
            "Xin chào! Tôi là trợ lý phân tích dữ liệu Banking/POS. "
            "Bạn có thể hỏi tôi về doanh thu, giao dịch, khách hàng, merchant, v.v. "
            "Ví dụ: 'Tổng doanh thu tháng 3 là bao nhiêu?'"
        )
    if any(w in q_lower for w in ("cảm ơn", "cám ơn", "thanks", "thank")):
        return "Không có gì! Nếu bạn cần hỏi thêm, cứ hỏi nhé."
    return "Tôi có thể giúp bạn truy vấn dữ liệu Banking/POS. Hãy đặt câu hỏi về dữ liệu!"


def _clarification_response(question: str) -> str:
    return (
        f"Câu hỏi '{question}' hơi chung chung. Bạn có thể cụ thể hơn không? "
        f"Ví dụ:\n"
        f"- 'Tổng số giao dịch tháng này là bao nhiêu?'\n"
        f"- 'Top 10 merchant có doanh thu cao nhất?'\n"
        f"- 'Danh sách khách hàng mới trong tháng 3?'"
    )


def _out_of_scope_response() -> str:
    return (
        "Xin lỗi, câu hỏi này nằm ngoài phạm vi dữ liệu Banking/POS. "
        "Tôi có thể giúp bạn phân tích doanh thu, giao dịch, khách hàng, "
        "merchant, thẻ, chuyển khoản, và các dữ liệu ngân hàng khác."
    )
