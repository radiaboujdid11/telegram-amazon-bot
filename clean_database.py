#!/usr/bin/env python3
"""
clean_database.py
Nettoie la BD Amazon - enlève les merdouilles, garde les VRAIS produits
"""

import sqlite3
import sys
from pathlib import Path


# Catégories À GARDER (vrais produits utiles)
GOOD_CATEGORIES = {
    # Vêtements
    'clothing', 'apparel', 'fashion', 'dress', 'shirt', 'pants', 'shoes',
    'jacket', 'coat', 'sweater', 'blouse', 'skirt', 'jeans',
    
    # Électronique
    'electronics', 'computers', 'laptop', 'phone', 'camera', 'headphones',
    'speaker', 'tablet', 'smartwatch', 'monitor', 'keyboard', 'mouse',
    'router', 'charger', 'cable',
    
    # Maison & Cuisine
    'home', 'kitchen', 'bedding', 'furniture', 'lamp', 'pillow', 'blanket',
    'cookware', 'utensils', 'towel', 'rug', 'chair', 'table', 'bed',
    
    # Sports & Loisirs
    'sports', 'outdoor', 'fitness', 'bicycle', 'yoga', 'swimming', 'camping',
    'hiking', 'ball', 'game', 'book', 'toy',
    
    # Beauté & Santé
    'beauty', 'health', 'skincare', 'makeup', 'perfume', 'sunscreen',
    'shampoo', 'moisturizer',
}

# Catégories À SUPPRIMER (inutile/pas vendable)
BAD_CATEGORIES = {
    'office supplies', 'stationery', 'pen', 'pencil', 'paper', 'notebook',
    'industrial', 'components', 'parts', 'accessories', 'fasteners',
    'bulk', 'wholesale', 'automotive parts', 'motorcycle parts',
    'tools', 'hardware', 'plumbing', 'electrical', 'lighting supplies',
}

# Mots-clés À SUPPRIMER (produits sans valeur)
BAD_KEYWORDS = {
    'bulk', 'wholesale', 'lot', 'pack of', '100 pieces', '50 pieces',
    'replacement part', 'component', 'screw', 'bolt', 'nut', 'washer',
    'cable tie', 'connector', 'adapter', 'circuit',
}

# Prix minimum pour être un VRAI produit vendable
MIN_PRICE = 5.0  # Plus de $5
MAX_PRICE = 5000.0  # Moins de $5000

# Longueur minimum du nom du produit (plus long = mieux décrit)
MIN_NAME_LENGTH = 15


def should_keep_product(name, category, price, reviews):
    """
    Décide si on garde ce produit ou on le supprime
    """
    
    if not name or not category:
        return False
    
    name_lower = name.lower()
    cat_lower = category.lower()
    
    # ❌ Supprime les prix bizarres
    if price is None or price < MIN_PRICE or price > MAX_PRICE:
        return False
    
    # ❌ Supprime les noms trop courts (génériques)
    if len(name) < MIN_NAME_LENGTH:
        return False
    
    # ❌ Supprime les catégories nulles
    if any(bad in cat_lower for bad in BAD_CATEGORIES):
        return False
    
    # ❌ Supprime les produits avec des mauvais mots-clés
    if any(bad in name_lower for bad in BAD_KEYWORDS):
        return False
    
    # ✅ Garde seulement les BONNES catégories
    if any(good in cat_lower for good in GOOD_CATEGORIES):
        return True
    
    return False


def clean_database():
    db_path = Path("products.db")
    
    if not db_path.exists():
        print("❌ products.db n'existe pas")
        return False
    
    print("🧹 NETTOYAGE DE LA BASE DE DONNÉES")
    print("="*60)
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Count before
    cursor.execute("SELECT COUNT(*) FROM products")
    before = cursor.fetchone()[0]
    print(f"\n📊 AVANT: {before:,} produits\n")
    
    # Find products to delete
    print("🔍 Analyse des produits...")
    cursor.execute("""
        SELECT id, asin, name, category_name, price, reviews
        FROM products
    """)
    
    products = cursor.fetchall()
    to_keep = []
    to_delete = []
    
    categories_kept = {}
    categories_deleted = {}
    
    for product_id, asin, name, category, price, reviews in products:
        if should_keep_product(name, category, price, reviews):
            to_keep.append(product_id)
            # Stats
            cat = category if category else "Unknown"
            categories_kept[cat] = categories_kept.get(cat, 0) + 1
        else:
            to_delete.append(product_id)
            # Stats
            cat = category if category else "Unknown"
            categories_deleted[cat] = categories_deleted.get(cat, 0) + 1
    
    print(f"✅ À GARDER: {len(to_keep):,} produits")
    print(f"❌ À SUPPRIMER: {len(to_delete):,} produits\n")
    
    # Show categories
    print("📂 TOP CATÉGORIES À GARDER:")
    for cat, count in sorted(categories_kept.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"   • {cat}: {count:,}")
    
    print("\n🗑️  TOP CATÉGORIES À SUPPRIMER:")
    for cat, count in sorted(categories_deleted.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"   • {cat}: {count:,}")
    
    # Confirm deletion
    print("\n" + "="*60)
    response = input(f"Supprimer {len(to_delete):,} produits? (y/n): ").lower()
    
    if response != 'y':
        print("Annulé.")
        conn.close()
        return False
    
    # Delete
    print("\n🔄 Suppression...")
    cursor.execute(f"""
        DELETE FROM products 
        WHERE id IN ({','.join(['?']*len(to_delete))})
    """, to_delete)
    
    conn.commit()
    
    # Verify
    cursor.execute("SELECT COUNT(*) FROM products")
    after = cursor.fetchone()[0]
    
    print(f"\n{'='*60}")
    print(f"📊 APRÈS: {after:,} produits")
    print(f"🗑️  Supprimé: {before - after:,} produits ({(before-after)/before*100:.1f}%)")
    print(f"✅ Gardé: {after:,} produits ({after/before*100:.1f}%)")
    print(f"{'='*60}\n")
    
    # Reindex
    print("📑 Réindexation...")
    conn.execute("VACUUM")
    conn.commit()
    
    conn.close()
    print("✅ Nettoyage terminé!\n")
    
    return True


if __name__ == "__main__":
    success = clean_database()
    sys.exit(0 if success else 1)
