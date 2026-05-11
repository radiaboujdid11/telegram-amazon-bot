"""
price_finder.py
Recherche optimisée dans products.db — 1.4M produits Amazon
"""

import sqlite3
import os
from typing import List, Dict, Optional
from difflib import SequenceMatcher


class PriceFinder:
    def __init__(self, db_path: str = "products.db"):
        self.db_path = db_path

    def search(self, query: str, max_results: int = 5,
               max_price: Optional[float] = None,
               category: Optional[str] = None,
               best_seller_only: bool = False) -> List[Dict]:

        if not os.path.exists(self.db_path):
            return []

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        words = [w for w in query.lower().split() if len(w) > 2]
        if not words:
            return []

        # Build WHERE clauses
        conditions = []
        params = []

        # Keyword search on name + category
        for w in words:
            conditions.append("(LOWER(name) LIKE ? OR LOWER(category_name) LIKE ?)")
            params += [f"%{w}%", f"%{w}%"]

        if max_price:
            conditions.append("price <= ?")
            params.append(max_price)

        if category:
            conditions.append("LOWER(category_name) LIKE ?")
            params.append(f"%{category.lower()}%")

        if best_seller_only:
            conditions.append("is_best_seller = 1")

        where = " AND ".join(conditions)

        rows = conn.execute(f"""
            SELECT asin, name, category_name, price, list_price,
                   stars, reviews, is_best_seller, bought_last_month,
                   url, image_url
            FROM products
            WHERE {where}
              AND price IS NOT NULL
              AND price > 0
            ORDER BY
                is_best_seller DESC,
                CASE WHEN stars >= 4.0 THEN 0 ELSE 1 END,
                stars DESC,
                reviews DESC
            LIMIT ?
        """, params + [max_results * 4]).fetchall()

        conn.close()

        # Score by relevance
        results = []
        for row in rows:
            score = SequenceMatcher(None, query.lower(), row["name"].lower()).ratio()
            results.append({**dict(row), "_score": score})

        results.sort(key=lambda x: (-x["_score"], -(x["stars"] or 0), -(x["reviews"] or 0)))

        return [self._clean(r) for r in results[:max_results]]

    def search_by_category(self, category: str, max_results: int = 5) -> List[Dict]:
        if not os.path.exists(self.db_path):
            return []
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT asin, name, category_name, price, list_price,
                   stars, reviews, is_best_seller, url, image_url
            FROM products
            WHERE LOWER(category_name) LIKE ?
              AND price IS NOT NULL AND price > 0
            ORDER BY is_best_seller DESC, stars DESC, reviews DESC
            LIMIT ?
        """, (f"%{category.lower()}%", max_results)).fetchall()
        conn.close()
        return [self._clean(dict(r)) for r in rows]

    def _clean(self, p: dict) -> dict:
        p.pop("_score", None)
        # Format price
        if p.get("price"):
            p["price_display"] = f"${p['price']:.2f}"
        if p.get("list_price") and p.get("price") and p["list_price"] > p["price"]:
            discount = round((1 - p["price"] / p["list_price"]) * 100)
            p["discount_display"] = f"-{discount}%"
            p["list_price_display"] = f"${p['list_price']:.2f}"
        return p

    def get_product_count(self) -> int:
        if not os.path.exists(self.db_path):
            return 0
        conn = sqlite3.connect(self.db_path)
        count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        conn.close()
        return count
