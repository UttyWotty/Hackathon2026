"""
Unit tests for the observability scoring module.

Tests all inline scorers (latency, token cost, SQL correctness) with
boundary conditions. LLM-as-judge tests use a stubbed MLX response
to avoid requiring a running model server.
"""

import json
from unittest.mock import MagicMock, patch

from services.infrastructure.observability.scoring import (
    LATENCY_EXCELLENT_SECONDS,
    LATENCY_GOOD_SECONDS,
    LATENCY_POOR_SECONDS,
    _extract_sql_block,
    score_latency,
    score_sql_correctness,
    score_token_cost,
)

# ---------------------------------------------------------------------------
# score_latency
# ---------------------------------------------------------------------------


class TestScoreLatency:
    """Tests for the latency scorer."""

    def test_excellent_latency(self) -> None:
        score, comment = score_latency(500.0)
        assert score == 1.0
        assert "Excellent" in comment

    def test_good_latency(self) -> None:
        score, comment = score_latency(3000.0)
        assert score == 0.8
        assert "Good" in comment

    def test_acceptable_latency(self) -> None:
        score, comment = score_latency(7000.0)
        assert score == 0.6
        assert "Acceptable" in comment

    def test_slow_latency(self) -> None:
        score, comment = score_latency(15000.0)
        assert score == 0.3
        assert "Slow" in comment

    def test_very_slow_latency(self) -> None:
        score, comment = score_latency(60000.0)
        assert score == 0.1
        assert "Very slow" in comment

    def test_boundary_excellent(self) -> None:
        score, _ = score_latency(LATENCY_EXCELLENT_SECONDS * 1000)
        assert score == 1.0

    def test_boundary_good(self) -> None:
        score, _ = score_latency(LATENCY_GOOD_SECONDS * 1000)
        assert score == 0.8

    def test_boundary_poor(self) -> None:
        score, _ = score_latency(LATENCY_POOR_SECONDS * 1000)
        assert score == 0.3

    def test_zero_latency(self) -> None:
        score, _ = score_latency(0.0)
        assert score == 1.0


# ---------------------------------------------------------------------------
# score_token_cost
# ---------------------------------------------------------------------------


class TestScoreTokenCost:
    """Tests for the token cost scorer."""

    def test_within_budget(self) -> None:
        score, comment = score_token_cost(1000, 500)
        assert score == 1.0
        assert "Within budget" in comment

    def test_at_budget(self) -> None:
        score, comment = score_token_cost(4000, 4000)
        assert score == 1.0

    def test_above_budget(self) -> None:
        score, comment = score_token_cost(6000, 4000)
        assert 0.3 <= score < 1.0
        assert "Above budget" in comment

    def test_expensive(self) -> None:
        score, comment = score_token_cost(10000, 10000)
        assert score == 0.1
        assert "Expensive" in comment

    def test_zero_tokens(self) -> None:
        score, _ = score_token_cost(0, 0)
        assert score == 1.0


# ---------------------------------------------------------------------------
# score_sql_correctness
# ---------------------------------------------------------------------------


class TestScoreSqlCorrectness:
    """Tests for the SQL correctness scorer."""

    def test_non_sql_output(self) -> None:
        score, comment = score_sql_correctness("This is a regular text response.")
        assert score == 1.0
        assert "skipped" in comment.lower()

    def test_valid_select(self) -> None:
        sql = "SELECT * FROM equipment WHERE id = '123'"
        score, comment = score_sql_correctness(sql)
        assert score == 1.0
        assert "read-only" in comment.lower()

    def test_valid_with_cte(self) -> None:
        sql = "WITH cte AS (SELECT id FROM shots) SELECT * FROM cte"
        score, comment = score_sql_correctness(sql)
        assert score == 1.0

    def test_markdown_code_block(self) -> None:
        text = "Here is the query:\n```sql\nSELECT name FROM users\n```"
        score, comment = score_sql_correctness(text)
        assert score == 1.0

    def test_dangerous_sql_in_select_fails(self) -> None:
        text = "SELECT * FROM users; DROP TABLE users;"
        score, comment = score_sql_correctness(text)
        assert score == 0.0
        assert "failed" in comment.lower()

    def test_non_select_sql_skipped(self) -> None:
        text = "DROP TABLE users"
        score, comment = score_sql_correctness(text)
        assert score == 1.0
        assert "skipped" in comment.lower()


# ---------------------------------------------------------------------------
# _extract_sql_block
# ---------------------------------------------------------------------------


class TestExtractSqlBlock:
    """Tests for SQL block extraction helper."""

    def test_markdown_block(self) -> None:
        text = "Query:\n```sql\nSELECT 1\n```"
        result = _extract_sql_block(text)
        assert result == "SELECT 1"

    def test_raw_select(self) -> None:
        text = "SELECT id, name FROM equipment WHERE status = 'active'"
        result = _extract_sql_block(text)
        assert result is not None
        assert "SELECT" in result

    def test_no_sql(self) -> None:
        text = "This is just a regular sentence."
        result = _extract_sql_block(text)
        assert result is None

    def test_with_clause(self) -> None:
        text = "WITH cte AS (SELECT 1) SELECT * FROM cte"
        result = _extract_sql_block(text)
        assert result is not None
        assert "WITH" in result


# ---------------------------------------------------------------------------
# LLM Judge (stubbed)
# ---------------------------------------------------------------------------


class TestLlmJudge:
    """Tests for LLM-as-judge with mocked MLX responses."""

    def _make_mock_response(self, score: float, reason: str) -> MagicMock:
        mock = MagicMock()
        mock.content = json.dumps({"score": score, "reason": reason})
        return mock

    @patch("services.infrastructure.observability.llm_judge._get_raw_llm")
    def test_judge_relevance(self, mock_get_llm: MagicMock) -> None:
        from services.infrastructure.observability.llm_judge import judge_relevance

        mock_llm = MagicMock()
        mock_llm.chat.return_value = self._make_mock_response(0.9, "Highly relevant")
        mock_get_llm.return_value = mock_llm

        score, reason = judge_relevance("Some LLM output text")
        assert 0.0 <= score <= 1.0
        assert isinstance(reason, str)
        mock_llm.chat.assert_called_once()

    @patch("services.infrastructure.observability.llm_judge._get_raw_llm")
    def test_judge_hallucination(self, mock_get_llm: MagicMock) -> None:
        from services.infrastructure.observability.llm_judge import (
            judge_hallucination_risk,
        )

        mock_llm = MagicMock()
        mock_llm.chat.return_value = self._make_mock_response(0.2, "Low risk")
        mock_get_llm.return_value = mock_llm

        score, reason = judge_hallucination_risk("Factual response with data")
        assert 0.0 <= score <= 1.0

    @patch("services.infrastructure.observability.llm_judge._get_raw_llm")
    def test_judge_domain_accuracy_with_terms(self, mock_get_llm: MagicMock) -> None:
        from services.infrastructure.observability.llm_judge import (
            judge_domain_accuracy,
        )

        mock_llm = MagicMock()
        mock_llm.chat.return_value = self._make_mock_response(0.95, "Correct OEE usage")
        mock_get_llm.return_value = mock_llm

        score, reason = judge_domain_accuracy("The OEE was 85% with MTTR of 2 hours")
        assert 0.0 <= score <= 1.0
        mock_llm.chat.assert_called_once()

    def test_judge_domain_accuracy_no_terms(self) -> None:
        from services.infrastructure.observability.llm_judge import (
            judge_domain_accuracy,
        )

        score, reason = judge_domain_accuracy("Hello, how are you today?")
        assert score == 1.0
        assert "not applicable" in reason.lower()

    @patch("services.infrastructure.observability.llm_judge._get_raw_llm")
    def test_judge_malformed_json(self, mock_get_llm: MagicMock) -> None:
        from services.infrastructure.observability.llm_judge import judge_relevance

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "I think this is pretty good, maybe 0.8 out of 1"
        mock_llm.chat.return_value = mock_response
        mock_get_llm.return_value = mock_llm

        score, reason = judge_relevance("Some output")
        assert 0.0 <= score <= 1.0

    @patch("services.infrastructure.observability.llm_judge._get_raw_llm")
    def test_judge_json_in_markdown(self, mock_get_llm: MagicMock) -> None:
        from services.infrastructure.observability.llm_judge import judge_relevance

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '```json\n{"score": 0.7, "reason": "Good"}\n```'
        mock_llm.chat.return_value = mock_response
        mock_get_llm.return_value = mock_llm

        score, reason = judge_relevance("Some output")
        assert score == 0.7
        assert reason == "Good"
