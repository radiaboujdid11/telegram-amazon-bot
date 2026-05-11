"""
price_finder_improved.py
Moteur de recherche AMÉLIORÉ - cherche SMART, pas juste par mots-clés
"""

import sqlite3
import os
from typing import List, Dict, Optional
from difflib import SequenceMatcher


class PriceFinder:
    def __init__(self, db_path: str = "products.db"):
        self.db_path = db_path
        
        # Catégories principales (pour améliorer les recherches)
        self.category_keywords = {
            'clothing': ['shirt', 't-shirt', 'dress', 'pants', 'jacket', 'coat', 'blouse', 'sweater', 'jeans', 'skirt'],
            'shoes': ['shoe', 'sneaker', 'boot', 'sandal', 'heel', 'loafer', 'slipper'],
            'electronics': ['laptop', 'phone', 'camera', 'headphone', 'speaker', 'tablet', 'watch', 'monitor'],
            'home': ['lamp', 'pillow', 'blanket', 'towel', 'rug', 'chair', 'table', 'bed', 'furniture'],
            'sports': ['ball', 'yoga', 'bike', 'bicycle', 'camping', 'hiking', 'swimming'],
        }

    def search(self, query: str, max_results: int = 5,
               max_price: Optional[float] = None,
               category: Optional[str] = None,
               best_seller_only: bool = False) -> List[Dict]:

        if not os.path.exists(self.db_path):
            return []

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        # Parse la requête
        words = [w for w in query.lower().split() if len(w) > 2]
        if not words:
            return []

        # Build WHERE clauses - AMÉLIORÉ
        conditions = []
        params = []

        # 1. Recherche par mots-clés (plus intelligent)
        for w in words:
            # Cherche dans le nom ET la catégorie
            conditions.append("""
                (LOWER(name) LIKE ? 
                 OR LOWER(category_name) LIKE ?
                 OR LOWER(name) LIKE ?)
            """)
            # %mot%, mot*, *mot
            params += [f"%{w}%", f"%{w}%", f"{w}%"]

        # 2. Détecte la catégorie automatiquement
        detected_category = self._detect_category(query)
        if detected_category and not category:
            category = detected_category

        if category:
            conditions.append("LOWER(category_name) LIKE ?")
            params.append(f"%{category.lower()}%")

        if max_price:
            conditions.append("price <= ?")
            params.append(max_price)

        if best_seller_only:
            conditions.append("is_best_seller = 1")

        # IMPORTANT: Exclure les produits sans prix ou très bon marché
        conditions.append("price >= 5.0")  # Min $5
        conditions.append("price <= 5000.0")  # Max $5000

        where = " AND ".join(conditions)

        # Recherche avec meilleur tri
        rows = conn.execute(f"""
            SELECT asin, name, category_name, price, list_price,
                   stars, reviews, is_best_seller, bought_last_month,
                   url, image_url
            FROM products
            WHERE {where}
              AND price IS NOT NULL
              AND price > 0
            ORDER BY
                -- 1. Best sellers en premier
                is_best_seller DESC,
                -- 2. Bonne note
                CASE WHEN stars >= 4.0 THEN 0 ELSE 1 END,
                -- 3. Plus de reviews = mieux
                reviews DESC,
                -- 4. Prix décent (pas trop cher, pas gratuit)
                ABS(price - 50) ASC
            LIMIT ?
        """, params + [max_results * 5]).fetchall()

        conn.close()

        if not rows:
            return []

        # Score par pertinence
        results = []
        for row in rows:
            # Calcule un score de pertinence
            name_match = SequenceMatcher(None, query.lower(), row["name"].lower()).ratio()
            category_match = 1.0 if detected_category and detected_category.lower() in row["category_name"].lower() else 0.5
            
            score = (name_match * 0.7) + (category_match * 0.3)
            
            results.append({
                **dict(row), 
                "_score": score
            })

        # Sort par score
        results.sort(key=lambda x: (-x["_score"], -(x["stars"] or 0), -(x["reviews"] or 0)))

        return [self._clean(r) for r in results[:max_results]]

    def _detect_category(self, query: str) -> Optional[str]:
        """
        Détecte automatiquement la catégorie basée sur les mots-clés
        """
        query_lower = query.lower()
        
        for category, keywords in self.category_keywords.items():
            for keyword in keywords:
                if keyword in query_lower:
                    return category
        
        return None

    def search_by_category(self, category: str, max_results: int = 5) -> List[Dict]:
        """Recherche dans une catégorie spécifique"""
        if not os.path.exists(self.db_path):
            return []
        
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        
        rows = conn.execute("""
            SELECT asin, name, category_name, price, list_price,
                   stars, reviews, is_best_seller, url, image_url
            FROM products
            WHERE LOWER(category_name) LIKE ?
              AND price IS NOT NULL 
              AND price > 0
              AND price >= 5.0
              AND price <= 5000.0
            ORDER BY 
                is_best_seller DESC, 
                stars DESC, 
                reviews DESC
            LIMIT ?
        """, (f"%{category.lower()}%", max_results)).fetchall()
        
        conn.close()
        
        return [self._clean(dict(r)) for r in rows]

    def get_popular_categories(self, limit: int = 10) -> List[tuple]:
        """Retourne les catégories les plus populaires"""
        if not os.path.exists(self.db_path):
            return []
        
        conn = sqlite3.connect(self.db_path)
        
        rows = conn.execute("""
            SELECT DISTINCT category_name, COUNT(*) as count
            FROM products
            WHERE price >= 5.0 AND price <= 5000.0
            GROUP BY category_name
            ORDER BY count DESC
            LIMIT ?
        """, (limit,)).fetchall()
        
        conn.close()
        
        return rows

    def _clean(self, p: dict) -> dict:
        """Nettoie et formate un produit"""
        p.pop("_score", None)
        
        if p.get("price"):
            p["price_display"] = f"${p['price']:.2f}"
        
        if p.get("list_price") and p.get("price") and p["list_price"] > p["price"]:
            discount = round((1 - p["price"] / p["list_price"]) * 100)
            p["discount_display"] = f"-{discount}%"
            p["list_price_display"] = f"${p['list_price']:.2f}"
        
        return p

    def get_product_count(self) -> int:
        """Compte total de produits"""
        if not os.path.exists(self.db_path):
            return 0
        
        conn = sqlite3.connect(self.db_path)
        count = conn.execute("SELECT COUNT(*) FROM products WHERE price >= 5.0 AND price <= 5000.0").fetchone()[0]
        conn.close()
        
        return count


# ─────────────────────────────────────────────────────────────────
# REMPLACE l'ancien price_finder.py par celui-ci!
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    finder = PriceFinder()
    
    print(f"Total produits: {finder.get_product_count():,}\n")
    
    # Test
    tests = ["shirt", "laptop", "shoes", "chamise a manches longues"]
    
    for test in tests:
        print(f"🔍 Recherche: '{test}'")
        results = finder.search(test, max_results=3)
        
        if results:
            for r in results:
                print(f"  ✅ {r['name'][:50]} - {r['price_display']}")
        else:
            print(f"  ❌ Pas de résultat")
        print()
