"""
load_data.py
Import Amazon dataset (1.4M products) + categories CSV → products.db
Colonnes produits : asin, title, imgUrl, productURL, stars, reviews,
                    price, listPrice, category_id, isBestSeller, boughtInLastMonth
Colonnes categories : id, category_name
Usage: python load_data.py
       python load_data.py data/amazon_products.csv data/amazon_categories.csv
"""

import sys
import sqlite3
import csv
import os
import re
from typing import Optional


def parse_float(s) -> Optional[float]:
    try:
        return float(re.sub(r"[^\d.]", "", str(s)))
    except (ValueError, AttributeError):
        return None


def parse_int(s) -> Optional[int]:
    try:
        return int(re.sub(r"[^\d]", "", str(s)))
    except (ValueError, AttributeError):
        return None


def parse_bool(s) -> int:
    return 1 if str(s).strip().lower() in ("true", "1", "yes") else 0


def load(
    products_csv: str = "data/amazon_products.csv",
    categories_csv: str = "data/amazon_categories.csv",
    db_path: str = "products.db",
):
    for f in [products_csv, categories_csv]:
        if not os.path.exists(f):
            print(f"❌ Fichier introuvable : {f}")
            sys.exit(1)

    conn = sqlite3.connect(db_path)

    # ── Categories ─────────────────────────────
    print("📂 Chargement des catégories...")
    conn.execute("DROP TABLE IF EXISTS categories")
    conn.execute("""
        CREATE TABLE categories (
            id            INTEGER PRIMARY KEY,
            category_name TEXT NOT NULL
        )
    """)
    cat_rows = []
    with open(categories_csv, encoding="utf-8", errors="ignore") as f:
        for row in csv.DictReader(f):
            cat_id = parse_int(row.get("id"))
            name = (row.get("category_name") or "").strip()
            if cat_id and name:
                cat_rows.append((cat_id, name))
    conn.executemany("INSERT OR IGNORE INTO categories (id, category_name) VALUES (?, ?)", cat_rows)
    print(f"   ✅ {len(cat_rows)} catégories")

    # ── Products ───────────────────────────────
    print("📦 Chargement des produits (peut prendre quelques minutes)...")
    conn.execute("DROP TABLE IF EXISTS products")
    conn.execute("""
        CREATE TABLE products (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            asin                TEXT,
            name                TEXT NOT NULL,
            category_id         INTEGER,
            category_name       TEXT,
            price               REAL,
            list_price          REAL,
            stars               REAL,
            reviews             INTEGER,
            is_best_seller      INTEGER DEFAULT 0,
            bought_last_month   INTEGER,
            url                 TEXT,
            image_url           TEXT
        )
    """)

    # Build category lookup
    cat_lookup = {row[0]: row[1] for row in cat_rows}

    rows = []
    skipped = 0
    BATCH = 10000

    with open(products_csv, encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("title") or "").strip()
            if not name or len(name) < 3:
                skipped += 1
                continue

            cat_id = parse_int(row.get("category_id"))
            cat_name = cat_lookup.get(cat_id) if cat_id else None
            price = parse_float(row.get("price"))
            list_price = parse_float(row.get("listPrice"))

            rows.append((
                (row.get("asin") or "").strip() or None,
                name,
                cat_id,
                cat_name,
                price,
                list_price,
                parse_float(row.get("stars")),
                parse_int(row.get("reviews")),
                parse_bool(row.get("isBestSeller", "")),
                parse_int(row.get("boughtInLastMonth")),
                (row.get("productURL") or "").strip() or None,
                (row.get("imgUrl") or "").strip() or None,
            ))

            # Batch insert
            if len(rows) >= BATCH:
                conn.executemany("""
                    INSERT INTO products
                        (asin, name, category_id, category_name, price, list_price,
                         stars, reviews, is_best_seller, bought_last_month, url, image_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, rows)
                conn.commit()
                print(f"   ... {conn.execute('SELECT COUNT(*) FROM products').fetchone()[0]:,} produits")
                rows = []

    # Last batch
    if rows:
        conn.executemany("""
            INSERT INTO products
                (asin, name, category_id, category_name, price, list_price,
                 stars, reviews, is_best_seller, bought_last_month, url, image_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)
        conn.commit()

    # Indexes for fast search
    print("🔍 Création des index...")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_name     ON products(name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_category ON products(category_name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_stars    ON products(stars)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_seller   ON products(is_best_seller)")
    conn.commit()

    total = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    conn.close()
    print(f"\n✅ {total:,} produits chargés ({skipped:,} ignorés) → {db_path}")


if __name__ == "__main__":
    products = sys.argv[1] if len(sys.argv) > 1 else "data/amazon_products.csv"
    categories = sys.argv[2] if len(sys.argv) > 2 else "data/amazon_categories.csv"
    load(products, categories)
