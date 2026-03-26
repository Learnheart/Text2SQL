"""Tests for the Router component — intent classification."""

import pytest
from src.models.schemas import IntentType
from src.pipeline.router import route


def _make_state(question: str) -> dict:
    return {"question": question}


class TestRouterSQLIntent:
    """Router should classify data queries as SQL intent."""

    def test_revenue_question_vi(self):
        state = route(_make_state("Tổng doanh thu tháng 3 là bao nhiêu?"))
        assert state["router_result"].intent == IntentType.SQL

    def test_count_question_vi(self):
        state = route(_make_state("Có bao nhiêu khách hàng mới trong tháng này?"))
        assert state["router_result"].intent == IntentType.SQL

    def test_top_question_vi(self):
        state = route(_make_state("Top 10 merchant có doanh thu cao nhất"))
        assert state["router_result"].intent == IntentType.SQL

    def test_comparison_question_en(self):
        state = route(_make_state("Compare revenue between Q1 and Q2"))
        assert state["router_result"].intent == IntentType.SQL

    def test_average_question_en(self):
        state = route(_make_state("What is the average transaction amount?"))
        assert state["router_result"].intent == IntentType.SQL

    def test_date_pattern(self):
        state = route(_make_state("Doanh số từ 2025-01 đến 2025-03"))
        assert state["router_result"].intent == IntentType.SQL

    def test_statistics_keyword(self):
        state = route(_make_state("Thống kê giao dịch theo quý"))
        assert state["router_result"].intent == IntentType.SQL

    def test_list_question(self):
        state = route(_make_state("Liệt kê tất cả chi nhánh"))
        assert state["router_result"].intent == IntentType.SQL

    def test_sql_confidence_high(self):
        state = route(_make_state("Tổng doanh thu tháng 1 là bao nhiêu?"))
        assert state["router_result"].confidence >= 0.7

    def test_domain_keyword_with_context(self):
        """Domain keyword + enough words should route to SQL."""
        state = route(_make_state("merchant nào bán nhiều nhất tháng này"))
        assert state["router_result"].intent == IntentType.SQL


class TestRouterChitchat:
    """Router should classify greetings and small talk as Chitchat."""

    def test_hello_vi(self):
        state = route(_make_state("Xin chào"))
        assert state["router_result"].intent == IntentType.CHITCHAT

    def test_hello_en(self):
        state = route(_make_state("Hello"))
        assert state["router_result"].intent == IntentType.CHITCHAT

    def test_thanks_vi(self):
        state = route(_make_state("Cảm ơn bạn"))
        assert state["router_result"].intent == IntentType.CHITCHAT

    def test_who_are_you(self):
        state = route(_make_state("Bạn là ai?"))
        assert state["router_result"].intent == IntentType.CHITCHAT

    def test_chitchat_has_message(self):
        state = route(_make_state("Xin chào"))
        assert state["router_result"].message != ""


class TestRouterClarification:
    """Router should ask for clarification on vague domain queries."""

    def test_vague_single_word(self):
        state = route(_make_state("giao dịch"))
        assert state["router_result"].intent == IntentType.CLARIFICATION

    def test_vague_short_query(self):
        state = route(_make_state("khách hàng"))
        assert state["router_result"].intent == IntentType.CLARIFICATION

    def test_clarification_has_message(self):
        state = route(_make_state("giao dịch"))
        assert state["router_result"].message != ""


class TestRouterOutOfScope:
    """Router should reject completely unrelated questions."""

    def test_weather(self):
        state = route(_make_state("Thời tiết hôm nay thế nào?"))
        assert state["router_result"].intent == IntentType.OUT_OF_SCOPE

    def test_recipe(self):
        state = route(_make_state("How to cook pasta?"))
        assert state["router_result"].intent == IntentType.OUT_OF_SCOPE

    def test_out_of_scope_has_message(self):
        state = route(_make_state("Thời tiết hôm nay"))
        assert state["router_result"].message != ""
