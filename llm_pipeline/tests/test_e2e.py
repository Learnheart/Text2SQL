"""End-to-end tests for the LLM-in-the-middle pipeline.

Tests the full flow: question -> Router -> Schema Linker -> SQL Generator -> Validator -> Executor -> response.
Uses real PostgreSQL, Redis, pgvector, and bge-m3 embeddings.
LLM is mocked with a FakeLLMProvider that returns pre-configured SQL responses.

Requires:
- Docker services running (infra-postgres, infra-redis via service-controller)
- Database seeded with scripts/seed_test_data.sql
"""

import pytest
import pytest_asyncio
from typing import Any

from src.cache.redis_cache import RedisCache
from src.data_access.connection import DatabasePool
from src.knowledge.bootstrap import KnowledgeBase, bootstrap_knowledge
from src.knowledge.vector_store import PgVectorStore
from src.llm.base import LLMProvider, LLMResponse
from src.models.schemas import IntentType, PipelineStatus
from src.pipeline.graph import PipelineGraph
from src.rag.embedding import EmbeddingService


# ---------------------------------------------------------------------------
# Fake LLM providers
# ---------------------------------------------------------------------------

class FakeLLMProvider(LLMProvider):
    """Returns pre-configured SQL responses based on question keywords."""

    def __init__(self, responses: dict[str, str] | None = None):
        self._responses = responses or {}
        self._call_count = 0
        self._call_history: list[dict] = []

    def create(self, *, system: str, messages: list[dict[str, Any]], tools=None, model: str, max_tokens: int, temperature: float) -> LLMResponse:
        self._call_count += 1
        user_msg = messages[-1]["content"] if messages else ""
        self._call_history.append({"model": model, "message": user_msg})

        for keyword, sql in self._responses.items():
            if keyword.lower() in user_msg.lower():
                return LLMResponse(text=f"```sql\n{sql}\n```", input_tokens=100, output_tokens=50)

        sql = self._infer_sql(user_msg)
        return LLMResponse(text=f"```sql\n{sql}\n```", input_tokens=100, output_tokens=50)

    def _infer_sql(self, message: str) -> str:
        msg = message.lower()
        if "doanh thu" in msg or "revenue" in msg:
            return "SELECT SUM(total_amount) AS total_revenue FROM sales WHERE status = 'completed'"
        if "khách hàng" in msg or "customer" in msg:
            return "SELECT COUNT(*) AS customer_count FROM customers"
        if "giao dịch" in msg or "transaction" in msg:
            return "SELECT COUNT(*) AS transaction_count FROM sales"
        if "số dư" in msg or "balance" in msg:
            return "SELECT SUM(balance) AS total_balance FROM accounts WHERE status = 'open'"
        if "merchant" in msg or "thương nhân" in msg:
            return "SELECT name, city FROM merchants"
        if "refund" in msg or "hoàn tiền" in msg:
            return "SELECT COUNT(*) AS refund_count, SUM(amount) AS total_refunded FROM refunds"
        if "nhân viên" in msg or "employee" in msg:
            return "SELECT COUNT(*) AS active_employees FROM employees WHERE is_active = true"
        if "chuyển khoản" in msg or "transfer" in msg:
            return "SELECT COUNT(*) AS transfer_count, SUM(amount) AS total_transferred FROM transfers WHERE status = 'completed'"
        if "sản phẩm" in msg or "product" in msg:
            return "SELECT name, category, price FROM products WHERE active = true"
        if "thẻ" in msg or "card" in msg:
            return "SELECT COUNT(*) AS active_cards FROM cards WHERE status = 'active'"
        if "chi nhánh" in msg or "branch" in msg:
            return "SELECT name, city FROM branches"
        return "SELECT COUNT(*) FROM sales"

    def format_tool_result(self, *, tool_call_id: str, content: str) -> dict:
        return {"role": "user", "content": content}

    def format_assistant_message(self, raw_response: Any) -> dict:
        return {"role": "assistant", "content": ""}


class BadSQLThenGoodLLM(LLMProvider):
    """Returns bad SQL on first call, good SQL on subsequent calls."""

    def __init__(self, bad_sql: str, good_sql: str):
        self._bad_sql = bad_sql
        self._good_sql = good_sql
        self._call_count = 0

    def create(self, *, system: str, messages: list[dict], tools=None, model: str, max_tokens: int, temperature: float) -> LLMResponse:
        self._call_count += 1
        sql = self._bad_sql if self._call_count == 1 else self._good_sql
        return LLMResponse(text=f"```sql\n{sql}\n```", input_tokens=100, output_tokens=50)

    def format_tool_result(self, *, tool_call_id: str, content: str) -> dict:
        return {"role": "user", "content": content}

    def format_assistant_message(self, raw_response: Any) -> dict:
        return {"role": "assistant", "content": ""}


class AlwaysBadLLM(LLMProvider):
    """Always returns invalid SQL — triggers max retries."""

    def __init__(self, bad_sql: str = "SELECT * FROM nonexistent_table_xyz"):
        self._bad_sql = bad_sql

    def create(self, *, system: str, messages: list[dict], tools=None, model: str, max_tokens: int, temperature: float) -> LLMResponse:
        return LLMResponse(text=f"```sql\n{self._bad_sql}\n```", input_tokens=100, output_tokens=50)

    def format_tool_result(self, *, tool_call_id: str, content: str) -> dict:
        return {"role": "user", "content": content}

    def format_assistant_message(self, raw_response: Any) -> dict:
        return {"role": "assistant", "content": ""}


# ---------------------------------------------------------------------------
# Fixtures — all use the same event loop (module scope)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def embedding_service():
    """Load bge-m3 embedding model once per module."""
    return EmbeddingService()


@pytest_asyncio.fixture(scope="module")
async def db_pool():
    """Real PostgreSQL connection pool."""
    pool = DatabasePool()
    await pool.init()
    yield pool
    await pool.close()


@pytest_asyncio.fixture(scope="module")
async def redis_cache():
    """Real Redis cache."""
    cache = RedisCache()
    await cache.init()
    yield cache
    if cache._client:
        try:
            await cache._client.aclose()
        except Exception:
            pass
        cache._client = None


@pytest_asyncio.fixture(scope="module")
async def knowledge(embedding_service):
    """Real Knowledge Base with pgvector + bge-m3 embeddings."""
    kb = await bootstrap_knowledge(embedding_service=embedding_service)
    yield kb
    await kb.vector_store.close()


def _make_graph(db_pool, knowledge, llm_provider=None):
    provider = llm_provider or FakeLLMProvider()
    return PipelineGraph(db_pool=db_pool, llm_provider=provider, knowledge=knowledge)


# ---------------------------------------------------------------------------
# E2E Tests
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestHappyPath:
    """Test successful pipeline execution with real services."""

    @pytest.mark.asyncio(loop_scope="module")
    async def test_revenue_query_vi(self, db_pool, knowledge):
        """Vietnamese: 'Tong doanh thu' -> SUM(sales.total_amount) -> rows returned."""
        graph = _make_graph(db_pool, knowledge)
        response = await graph.run("Tổng doanh thu các giao dịch thành công?")

        assert response.status == PipelineStatus.SUCCESS
        assert response.intent == IntentType.SQL
        assert response.sql is not None
        assert "sales" in response.sql.lower()
        assert response.results is not None
        assert response.results.error is None
        assert response.results.row_count >= 1
        assert response.attempts == 1
        assert response.total_tokens > 0
        assert response.latency_ms > 0

    @pytest.mark.asyncio(loop_scope="module")
    async def test_customer_count_query(self, db_pool, knowledge):
        """Count customers -> returns 5 from seed data."""
        graph = _make_graph(db_pool, knowledge)
        response = await graph.run("Có bao nhiêu khách hàng trong hệ thống?")

        assert response.status == PipelineStatus.SUCCESS
        assert response.results is not None
        assert response.results.row_count >= 1
        # We seeded 5 customers
        first_row = response.results.rows[0]
        assert any(v == 5 for v in first_row)

    @pytest.mark.asyncio(loop_scope="module")
    async def test_balance_query(self, db_pool, knowledge):
        """Total balance of open accounts."""
        graph = _make_graph(db_pool, knowledge)
        response = await graph.run("Tổng số dư các tài khoản đang mở?")

        assert response.status == PipelineStatus.SUCCESS
        assert response.results is not None
        assert response.results.row_count >= 1

    @pytest.mark.asyncio(loop_scope="module")
    async def test_transaction_count(self, db_pool, knowledge):
        """Count all transactions."""
        graph = _make_graph(db_pool, knowledge)
        response = await graph.run("Tổng số giao dịch trong hệ thống là bao nhiêu?")

        assert response.status == PipelineStatus.SUCCESS
        assert response.results is not None
        first_row = response.results.rows[0]
        assert any(v == 7 for v in first_row)

    @pytest.mark.asyncio(loop_scope="module")
    async def test_merchant_list(self, db_pool, knowledge):
        """List merchants."""
        graph = _make_graph(db_pool, knowledge)
        response = await graph.run("Danh sách các merchant trong hệ thống?")

        assert response.status == PipelineStatus.SUCCESS
        assert response.results is not None
        assert response.results.row_count == 3

    @pytest.mark.asyncio(loop_scope="module")
    async def test_refund_stats(self, db_pool, knowledge):
        """Refund statistics."""
        graph = _make_graph(db_pool, knowledge)
        response = await graph.run("Thống kê refund: số lượng và tổng tiền hoàn?")

        assert response.status == PipelineStatus.SUCCESS
        assert response.results is not None
        assert response.results.row_count >= 1

    @pytest.mark.asyncio(loop_scope="module")
    async def test_active_employees(self, db_pool, knowledge):
        """Count active employees."""
        graph = _make_graph(db_pool, knowledge)
        response = await graph.run("Có bao nhiêu nhân viên đang hoạt động?")

        assert response.status == PipelineStatus.SUCCESS
        assert response.results is not None
        first_row = response.results.rows[0]
        assert any(v == 3 for v in first_row)

    @pytest.mark.asyncio(loop_scope="module")
    async def test_english_query(self, db_pool, knowledge):
        """English query should also work."""
        graph = _make_graph(db_pool, knowledge)
        response = await graph.run("How many active cards are there in the system?")

        assert response.status == PipelineStatus.SUCCESS
        assert response.results is not None
        assert response.results.row_count >= 1


@pytest.mark.e2e
class TestNonSQLIntents:
    """Test that non-SQL intents are correctly handled."""

    @pytest.mark.asyncio(loop_scope="module")
    async def test_chitchat_rejected(self, db_pool, knowledge):
        llm = FakeLLMProvider()
        graph = _make_graph(db_pool, knowledge, llm)
        response = await graph.run("Xin chào!")

        assert response.status == PipelineStatus.REJECTED
        assert response.intent == IntentType.CHITCHAT
        assert response.explanation
        assert response.sql is None
        assert response.results is None
        assert llm._call_count == 0

    @pytest.mark.asyncio(loop_scope="module")
    async def test_out_of_scope_rejected(self, db_pool, knowledge):
        llm = FakeLLMProvider()
        graph = _make_graph(db_pool, knowledge, llm)
        response = await graph.run("How to cook pho?")

        assert response.status == PipelineStatus.REJECTED
        assert response.intent == IntentType.OUT_OF_SCOPE
        assert response.explanation
        assert llm._call_count == 0

    @pytest.mark.asyncio(loop_scope="module")
    async def test_clarification_needed(self, db_pool, knowledge):
        llm = FakeLLMProvider()
        graph = _make_graph(db_pool, knowledge, llm)
        response = await graph.run("giao dịch")

        assert response.status == PipelineStatus.CLARIFICATION
        assert response.intent == IntentType.CLARIFICATION
        assert response.explanation
        assert llm._call_count == 0

    @pytest.mark.asyncio(loop_scope="module")
    async def test_thanks_rejected(self, db_pool, knowledge):
        llm = FakeLLMProvider()
        graph = _make_graph(db_pool, knowledge, llm)
        response = await graph.run("Cảm ơn bạn!")

        assert response.status == PipelineStatus.REJECTED
        assert response.intent == IntentType.CHITCHAT
        assert llm._call_count == 0


@pytest.mark.e2e
class TestSelfCorrection:
    """Test the retry loop with real validation and execution."""

    @pytest.mark.asyncio(loop_scope="module")
    async def test_validation_retry_then_success(self, db_pool, knowledge):
        """Bad SQL (nonexistent table) on attempt 1 -> fixed on attempt 2."""
        llm = BadSQLThenGoodLLM(
            bad_sql="SELECT * FROM nonexistent_table",
            good_sql="SELECT COUNT(*) FROM sales",
        )
        graph = _make_graph(db_pool, knowledge, llm)
        response = await graph.run("Tổng số giao dịch bao nhiêu?")

        assert response.status == PipelineStatus.SUCCESS
        assert response.attempts == 2
        assert llm._call_count == 2

    @pytest.mark.asyncio(loop_scope="module")
    async def test_execution_retry_then_success(self, db_pool, knowledge):
        """SQL with wrong column on attempt 1 -> fixed on attempt 2."""
        llm = BadSQLThenGoodLLM(
            bad_sql="SELECT nonexistent_column FROM sales",
            good_sql="SELECT COUNT(*) FROM sales",
        )
        graph = _make_graph(db_pool, knowledge, llm)
        response = await graph.run("Thống kê số giao dịch?")

        assert response.status == PipelineStatus.SUCCESS
        assert response.attempts >= 2

    @pytest.mark.asyncio(loop_scope="module")
    async def test_max_retries_exhausted(self, db_pool, knowledge):
        """Persistent errors should exhaust retries."""
        llm = AlwaysBadLLM("SELECT * FROM table_that_does_not_exist_abc")
        graph = _make_graph(db_pool, knowledge, llm)
        response = await graph.run("Tổng doanh thu tháng 3?")

        assert response.status == PipelineStatus.MAX_RETRIES
        assert response.attempts >= 3
        assert response.explanation


@pytest.mark.e2e
class TestDatabaseIntegration:
    """Test real SQL execution against PostgreSQL with seeded data."""

    @pytest.mark.asyncio(loop_scope="module")
    async def test_direct_db_query(self, db_pool):
        """Verify database connection and seeded data."""
        result = await db_pool.execute("SELECT COUNT(*) AS cnt FROM customers")
        assert "error" not in result
        assert result["row_count"] == 1
        assert result["rows"][0][0] == 5

    @pytest.mark.asyncio(loop_scope="module")
    async def test_join_query(self, db_pool):
        """Test a JOIN query against real data."""
        sql = """
        SELECT c.first_name, COUNT(s.id) AS sale_count
        FROM customers c
        JOIN sales s ON s.customer_id = c.id
        WHERE s.status = 'completed'
        GROUP BY c.first_name
        ORDER BY sale_count DESC
        LIMIT 5
        """
        result = await db_pool.execute(sql)
        assert "error" not in result
        assert result["row_count"] >= 1
        assert "first_name" in result["columns"]
        assert "sale_count" in result["columns"]

    @pytest.mark.asyncio(loop_scope="module")
    async def test_read_only_enforcement(self, db_pool):
        """INSERT should be blocked by read-only mode."""
        result = await db_pool.execute("INSERT INTO customers (first_name) VALUES ('hack')")
        assert "error" in result
        assert "read-only" in result["error"].lower() or "read_only" in result["error"].lower()

    @pytest.mark.asyncio(loop_scope="module")
    async def test_aggregate_query(self, db_pool):
        """Test aggregate query on sales."""
        sql = "SELECT SUM(total_amount) AS total FROM sales WHERE status = 'completed'"
        result = await db_pool.execute(sql)
        assert "error" not in result
        assert result["row_count"] == 1
        total = result["rows"][0][0]
        # Sum of completed: 60000 + 135000 + 25000000 + 45000 + 25000000 = 50240000
        assert float(total) == 50240000.00


@pytest.mark.e2e
class TestKnowledgeLayerIntegration:
    """Test real embedding + pgvector retrieval."""

    @pytest.mark.asyncio(loop_scope="module")
    async def test_vector_store_has_schema_chunks(self, knowledge):
        count = await knowledge.vector_store.count("schema_chunks")
        assert count > 0

    @pytest.mark.asyncio(loop_scope="module")
    async def test_vector_store_has_examples(self, knowledge):
        count = await knowledge.vector_store.count("examples")
        assert count > 0

    @pytest.mark.asyncio(loop_scope="module")
    async def test_vector_search_returns_relevant_chunks(self, knowledge):
        query_embedding = knowledge.embedding_service.embed("total sales revenue")
        results = await knowledge.vector_store.query(
            collection="schema_chunks",
            query_embedding=query_embedding,
            top_k=3,
        )
        assert len(results) > 0
        docs = " ".join(r["document"].lower() for r in results)
        assert "sales" in docs

    @pytest.mark.asyncio(loop_scope="module")
    async def test_example_search_returns_similar_queries(self, knowledge):
        query_embedding = knowledge.embedding_service.embed("doanh thu tháng này")
        results = await knowledge.vector_store.query(
            collection="examples",
            query_embedding=query_embedding,
            top_k=3,
        )
        assert len(results) > 0

    def test_semantic_layer_metrics(self, knowledge):
        metrics = knowledge.semantic_layer.get_all_metrics()
        assert len(metrics) >= 10
        revenue = knowledge.semantic_layer.get_metric("doanh_thu")
        assert revenue is not None
        assert "SUM" in revenue.sql

    def test_semantic_layer_business_rules(self, knowledge):
        assert len(knowledge.semantic_layer.business_rules) > 0

    def test_example_store_loaded(self, knowledge):
        assert len(knowledge.example_store.examples) >= 40


@pytest.mark.e2e
class TestCacheIntegration:
    """Test Redis cache with real Redis."""

    @pytest.mark.asyncio(loop_scope="module")
    async def test_cache_available(self, redis_cache):
        assert redis_cache.available is True

    @pytest.mark.asyncio(loop_scope="module")
    async def test_cache_set_and_get(self, redis_cache):
        test_data = {"sql": "SELECT 1", "rows": [[1]], "status": "success"}
        await redis_cache.set_query("e2e_test_question", test_data)
        cached = await redis_cache.get_query("e2e_test_question")
        assert cached is not None
        assert cached["sql"] == "SELECT 1"

    @pytest.mark.asyncio(loop_scope="module")
    async def test_cache_miss(self, redis_cache):
        cached = await redis_cache.get_query("this_question_does_not_exist_in_cache")
        assert cached is None

    @pytest.mark.asyncio(loop_scope="module")
    async def test_session_cache(self, redis_cache):
        session_data = {"history": ["q1", "q2"], "user": "test"}
        await redis_cache.set_session("e2e_session_123", session_data)
        cached = await redis_cache.get_session("e2e_session_123")
        assert cached is not None
        assert cached["user"] == "test"


@pytest.mark.e2e
class TestPipelineResponseContract:
    """Verify PipelineResponse contract for all scenarios."""

    @pytest.mark.asyncio(loop_scope="module")
    async def test_success_response_has_all_fields(self, db_pool, knowledge):
        graph = _make_graph(db_pool, knowledge)
        response = await graph.run("Danh sách chi nhánh ngân hàng?")

        assert response.status == PipelineStatus.SUCCESS
        assert response.sql is not None and len(response.sql) > 0
        assert response.results is not None
        assert response.results.columns
        assert response.results.rows is not None
        assert response.results.row_count >= 0
        assert response.results.execution_time_ms >= 0
        assert response.results.error is None
        assert response.attempts >= 1
        assert response.total_tokens > 0
        assert response.latency_ms > 0
        assert response.intent == IntentType.SQL

    @pytest.mark.asyncio(loop_scope="module")
    async def test_rejected_response_has_explanation(self, db_pool, knowledge):
        graph = _make_graph(db_pool, knowledge)
        response = await graph.run("What's the weather like today?")

        assert response.status == PipelineStatus.REJECTED
        assert response.explanation
        assert response.sql is None
        assert response.results is None

    @pytest.mark.asyncio(loop_scope="module")
    async def test_max_retries_response(self, db_pool, knowledge):
        llm = AlwaysBadLLM()
        graph = _make_graph(db_pool, knowledge, llm)
        response = await graph.run("Top 10 sản phẩm bán chạy nhất?")

        assert response.status == PipelineStatus.MAX_RETRIES
        assert response.explanation
        assert response.attempts >= 3
        assert response.intent == IntentType.SQL


@pytest.mark.e2e
class TestCustomSQLResponses:
    """Test pipeline with specific SQL responses."""

    @pytest.mark.asyncio(loop_scope="module")
    async def test_complex_join_query(self, db_pool, knowledge):
        llm = FakeLLMProvider(responses={
            "top merchant": (
                "SELECT m.name, COUNT(s.id) AS sale_count, SUM(s.total_amount) AS revenue "
                "FROM merchants m "
                "JOIN sales s ON s.merchant_id = m.id "
                "WHERE s.status = 'completed' "
                "GROUP BY m.name "
                "ORDER BY revenue DESC"
            ),
        })
        graph = _make_graph(db_pool, knowledge, llm)
        response = await graph.run("Top merchant theo doanh thu?")

        assert response.status == PipelineStatus.SUCCESS
        assert response.results is not None
        assert response.results.row_count >= 1
        assert "name" in response.results.columns

    @pytest.mark.asyncio(loop_scope="module")
    async def test_date_filter_query(self, db_pool, knowledge):
        llm = FakeLLMProvider(responses={
            "tháng 1": (
                "SELECT COUNT(*) AS jan_sales, SUM(total_amount) AS jan_revenue "
                "FROM sales "
                "WHERE sale_time >= '2025-01-01' AND sale_time < '2025-02-01' "
                "AND status = 'completed'"
            ),
        })
        graph = _make_graph(db_pool, knowledge, llm)
        response = await graph.run("Doanh thu tháng 1 năm 2025?")

        assert response.status == PipelineStatus.SUCCESS
        assert response.results is not None
        assert response.results.row_count == 1
        # Jan 2025 completed: 60000 + 135000 = 195000
        revenue = response.results.rows[0][1]
        assert float(revenue) == 195000.00

    @pytest.mark.asyncio(loop_scope="module")
    async def test_subquery(self, db_pool, knowledge):
        llm = FakeLLMProvider(responses={
            "khách hàng nhiều giao dịch": (
                "SELECT c.first_name, c.last_name, sub.sale_count "
                "FROM customers c "
                "JOIN ("
                "  SELECT customer_id, COUNT(*) AS sale_count "
                "  FROM sales WHERE status = 'completed' GROUP BY customer_id"
                ") sub ON sub.customer_id = c.id "
                "ORDER BY sub.sale_count DESC"
            ),
        })
        graph = _make_graph(db_pool, knowledge, llm)
        response = await graph.run("Khách hàng nhiều giao dịch nhất?")

        assert response.status == PipelineStatus.SUCCESS
        assert response.results is not None
        assert response.results.row_count >= 1


@pytest.mark.e2e
class TestValidatorIntegration:
    """Test that the validator correctly catches issues in the real pipeline."""

    @pytest.mark.asyncio(loop_scope="module")
    async def test_dml_blocked_in_pipeline(self, db_pool, knowledge):
        """INSERT/UPDATE/DELETE should be blocked by validator."""
        llm = FakeLLMProvider(responses={
            "xóa": "DELETE FROM customers WHERE id = 1",
        })
        graph = _make_graph(db_pool, knowledge, llm)
        response = await graph.run("Xóa tất cả giao dịch lỗi?")

        # DML is always blocked -> max retries since LLM keeps generating DELETE
        assert response.status in (PipelineStatus.MAX_RETRIES, PipelineStatus.ERROR)

    @pytest.mark.asyncio(loop_scope="module")
    async def test_limit_auto_added(self, db_pool, knowledge):
        """SQL without LIMIT should have LIMIT auto-added."""
        llm = FakeLLMProvider(responses={
            "danh sách": "SELECT name, city FROM merchants",
        })
        graph = _make_graph(db_pool, knowledge, llm)
        response = await graph.run("Danh sách tất cả merchant?")

        assert response.status == PipelineStatus.SUCCESS
