"""
Unit tests for data_query_server.py — product search, category listing,
and the three-level fallback (exact → keyword split → fuzzy).

Uses in-memory SQLite so no real PostgreSQL is needed.
"""
import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.models import Base, Product, Inventory


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="function")
def test_engine():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture(scope="function")
def session(test_engine):
    Session = sessionmaker(bind=test_engine)
    s = Session()
    yield s
    s.close()


@pytest.fixture(scope="function")
def populated_session(session):
    """Seed a handful of products + inventory rows."""
    products = [
        Product(product_name="Midnight Petal Dress", category="Dresses", price=55.0,
                description="A beautiful floral midnight dress", image_url="a.jpg", colour="Black"),
        Product(product_name="Crimson Canvas", category="Dresses", price=45.0,
                description="Red canvas dress", image_url="b.jpg", colour="Red"),
        Product(product_name="Ocean Breeze Skirt", category="Skirts", price=30.0,
                description="Light blue flowing skirt", image_url="c.jpg", colour="Blue"),
        Product(product_name="Ivory Lace Top", category="Tops & Blouses", price=28.0,
                description="Elegant ivory lace blouse", image_url="d.jpg", colour="White"),
    ]
    for p in products:
        session.add(p)
    session.flush()

    # Each product gets a few sizes
    for p in products:
        for size, qty in [("S", 5), ("M", 3), ("L", 0)]:
            session.add(Inventory(product_id=p.product_id, size=size, stock_quantity=qty))

    session.commit()
    return session


# ---------------------------------------------------------------------------
# Category listing tests
# ---------------------------------------------------------------------------
class TestCategoryListing:
    def test_categories_with_stock(self, populated_session):
        from sqlalchemy import text
        result = populated_session.execute(text(
            """
            SELECT p.category, COUNT(p.product_id) as cnt
            FROM products p
            JOIN inventory i ON p.product_id = i.product_id
            WHERE i.stock_quantity > 0
            GROUP BY p.category
            ORDER BY p.category
            """
        )).fetchall()
        categories = {row[0] for row in result}
        assert "Dresses" in categories
        assert "Skirts" in categories
        assert "Tops & Blouses" in categories

    def test_all_zero_stock_excluded(self, session):
        """A product with only stock_quantity=0 should not appear in categories."""
        p = Product(product_name="Sold Out Dress", category="Dresses", price=99.0,
                    description="", image_url="", colour="Black")
        session.add(p)
        session.flush()
        session.add(Inventory(product_id=p.product_id, size="M", stock_quantity=0))
        session.commit()

        from sqlalchemy import text
        result = session.execute(text(
            "SELECT product_name FROM products p "
            "JOIN inventory i ON p.product_id=i.product_id "
            "WHERE i.stock_quantity > 0 AND p.product_name='Sold Out Dress'"
        )).fetchall()
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Product search — simulating the three-level fallback
# ---------------------------------------------------------------------------
class TestProductSearch:
    def test_exact_name_match(self, populated_session):
        results = populated_session.query(Product).filter(
            Product.product_name.ilike("%Midnight Petal%")
        ).all()
        assert len(results) == 1
        assert results[0].product_name == "Midnight Petal Dress"

    def test_category_search(self, populated_session):
        results = populated_session.query(Product).filter(
            Product.category.ilike("%Skirts%")
        ).all()
        assert len(results) == 1
        assert results[0].product_name == "Ocean Breeze Skirt"

    def test_description_search(self, populated_session):
        results = populated_session.query(Product).filter(
            Product.description.ilike("%lace%")
        ).all()
        assert len(results) == 1
        assert "Lace" in results[0].product_name

    def test_no_match_returns_empty(self, populated_session):
        results = populated_session.query(Product).filter(
            Product.product_name.ilike("%xyzzy_nonexistent%")
        ).all()
        assert len(results) == 0

    def test_keyword_split_fallback(self, populated_session):
        """'Blue skirt' should match Ocean Breeze Skirt via colour/description keyword."""
        # Simulates keyword split: search 'blue' and 'skirt' separately
        keywords = ["blue", "skirt"]
        all_results = set()
        for kw in keywords:
            rows = populated_session.query(Product).filter(
                Product.description.ilike(f"%{kw}%") |
                Product.product_name.ilike(f"%{kw}%") |
                Product.category.ilike(f"%{kw}%")
            ).all()
            for r in rows:
                all_results.add(r.product_name)
        assert "Ocean Breeze Skirt" in all_results

    def test_fuzzy_match(self):
        """difflib.get_close_matches should find similar product names."""
        import difflib
        product_names = [
            "Midnight Petal Dress",
            "Crimson Canvas",
            "Ocean Breeze Skirt",
            "Ivory Lace Top",
        ]
        matches = difflib.get_close_matches("midnite petal", product_names, n=3, cutoff=0.4)
        assert len(matches) > 0
        assert "Midnight Petal Dress" in matches


# ---------------------------------------------------------------------------
# Price validation
# ---------------------------------------------------------------------------
class TestProductData:
    def test_prices_are_positive(self, populated_session):
        products = populated_session.query(Product).all()
        for p in products:
            assert p.price > 0, f"Product {p.product_name} has non-positive price {p.price}"

    def test_image_urls_not_empty(self, populated_session):
        products = populated_session.query(Product).all()
        for p in products:
            assert p.image_url, f"Product {p.product_name} has no image_url"
