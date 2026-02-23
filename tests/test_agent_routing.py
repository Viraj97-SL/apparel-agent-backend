"""
Unit tests for agent routing logic.

We test the supervisor's routing decisions by checking that the right
keywords map to the right agents. These are pure-logic tests — no LLM
calls, no DB, no actual agent execution.
"""
import pytest
import re


# ---------------------------------------------------------------------------
# Routing oracle — mirrors the intent of the supervisor prompt.
# In a real integration test you would call the supervisor node directly;
# here we verify that the classification heuristics are correct so the
# prompt can be updated with confidence.
# ---------------------------------------------------------------------------
BUYING_PATTERNS = re.compile(
    # "order" alone is too broad — "my order", "order status" are policy questions.
    # Use "place an order" / "order now" or rely on "buy" / "purchase" / "i want".
    r"\b(buy|purchase|add to cart|i want|checkout|confirm)\b", re.IGNORECASE
)
BROWSING_PATTERNS = re.compile(
    r"\b(show me|do you have|browse|list|what (do you sell|categories)|price of|in stock|sizes?)\b",
    re.IGNORECASE,
)
POLICY_PATTERNS = re.compile(
    r"\b(return|refund|delivery|shipping|policy|exchange|how long|when will|guarantee|order status)\b",
    re.IGNORECASE,
)
# Note: patterns ending with ":" must NOT have a trailing \b because ":" is a
# non-word char and the char after it (space or digit) may also be non-word,
# making the boundary check fail.  Use \bword\s*: lookahead instead.
PERSONAL_DETAIL_PATTERNS = re.compile(
    r"(\bmy name is\b|\baddress\s*:|\bphone\s*:|\bnumber\s*:|\bfrom\s+[a-z]|\bname\s*:[a-z])", re.IGNORECASE
)


def classify_intent(text: str) -> str:
    """Simplified rule-based intent classifier matching supervisor priorities."""
    if BUYING_PATTERNS.search(text) or PERSONAL_DETAIL_PATTERNS.search(text):
        return "sales_agent"
    if BROWSING_PATTERNS.search(text):
        return "data_query_agent"
    if POLICY_PATTERNS.search(text):
        return "rag_agent"
    return "rag_agent"  # default to policy/chat for greetings etc.


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestBuyingIntent:
    @pytest.mark.parametrize("query", [
        "I want to buy the blue dress",
        "I'd like to purchase a skirt",
        "Add to cart please",
        "I want it in size M",
        "Can I buy the Crimson Canvas?",
        "I want to checkout",
    ])
    def test_buying_routes_to_sales(self, query):
        assert classify_intent(query) == "sales_agent", f"Expected sales_agent for: {query!r}"

    @pytest.mark.parametrize("detail", [
        "My name is Sarah",
        "Address: 10 Baker Street London",
        "Phone: 07700900000",
        "Name:Viraj, Address:Eheliyagoda, Number:071791300",
    ])
    def test_personal_details_route_to_sales(self, detail):
        assert classify_intent(detail) == "sales_agent", f"Expected sales_agent for: {detail!r}"


class TestBrowsingIntent:
    @pytest.mark.parametrize("query", [
        "Show me dresses",
        "Do you have skirts?",
        "What do you sell?",
        "List your tops",
        "What categories do you have?",
        "Price of the Midnight Petal",
        "Is the blue skirt in stock?",
        "What sizes does it come in?",
    ])
    def test_browsing_routes_to_data_query(self, query):
        assert classify_intent(query) == "data_query_agent", f"Expected data_query_agent for: {query!r}"


class TestPolicyIntent:
    @pytest.mark.parametrize("query", [
        "What is your return policy?",
        "How long does delivery take?",
        "Can I get a refund?",
        "Do you do exchanges?",
        "When will my order ship?",
        "Is there a guarantee?",
    ])
    def test_policy_routes_to_rag(self, query):
        assert classify_intent(query) == "rag_agent", f"Expected rag_agent for: {query!r}"


class TestCompositePriority:
    def test_buy_overrides_browse(self):
        """Buying intent should win over browsing intent in composite messages."""
        query = "Do you have the blue dress? I want to buy it."
        assert classify_intent(query) == "sales_agent"

    def test_return_policy_is_rag(self):
        """Clearly policy — not buying or browsing."""
        query = "What is the return policy for dresses?"
        assert classify_intent(query) == "rag_agent"
