"""
ai_assistant.py
Groq (llama-3.3-70b) — assistant shopping avec mémoire et recherche précise
"""

import re
from groq import Groq
from typing import List, Dict, Optional
from database import Database
from price_finder import PriceFinder
from config import Config


class AIAssistant:
    def __init__(self):
        self.client = Groq(api_key=Config.GROQ_API_KEY)
        self.db = Database()
        self.finder = PriceFinder()
        self._conversations: Dict[int, List[Dict]] = {}

    # ── System Prompt ──────────────────────────

    def _system_prompt(self, user_id: int) -> str:
        stats = self.db.get_user_stats(user_id)
        history = self.db.get_user_history(user_id, limit=8)
        prefs = self.db.get_user_preferences(user_id) or {}

        recent = ", ".join(s["product_name"] for s in history[:5]) if history else "aucune"
        budget = prefs.get("budget", "non précisé")
        fav_cats = prefs.get("favorite_categories", [])
        product_count = self.finder.get_product_count()

        return f"""Tu es un assistant shopping Amazon expert, précis et efficace.
Tu parles français par défaut (adapte-toi à la langue de l'utilisateur).
Tu as accès à une base de {product_count:,} produits Amazon réels avec prix et liens directs.

## Profil utilisateur
- Recherches totales : {stats['total_searches']}
- Recherches récentes : {recent}
- Budget habituel : {budget}
- Catégories favorites : {', '.join(fav_cats) if fav_cats else 'non détectées'}

## RÈGLES IMPORTANTES
1. Réponds UNIQUEMENT avec les produits fournis dans le contexte [Produits trouvés]
2. Si aucun produit ne correspond exactement, DIS-LE clairement — ne propose pas des produits hors sujet
3. Extrais toujours le budget depuis le message (ex: "sous 50€", "moins de 100$")
4. Mentionne TOUJOURS le lien URL du produit pour que l'utilisateur puisse acheter
5. Si l'utilisateur cherche un produit absent de la base, suggère des termes alternatifs

## Format de réponse
🔸 **[Nom du produit court]**
   💰 [prix réduit] ~~[prix original]~~ [% réduction si dispo]
   ⭐ [note]/5 ([nb avis] avis) [🏆 Best Seller si applicable]
   🔗 [URL Amazon]
   ✅ [1 phrase pourquoi c'est le bon choix]

## Comportement
- Maximum 3-5 produits par réponse
- Si budget détecté → filtre les produits hors budget
- Trie par meilleur rapport qualité/prix
- Sois direct et concis — l'utilisateur est sur mobile
"""

    # ── Chat ───────────────────────────────────

    def chat(self, user_id: int, user_message: str) -> str:
        if user_id not in self._conversations:
            self._conversations[user_id] = []

        # Extract filters from message
        budget = self._extract_budget(user_message)
        keywords = self._extract_keywords(user_message)

        # Search with filters
        search_context = ""
        if keywords:
            results = self.finder.search(
                keywords,
                max_results=6,
                max_price=budget,
            )
            search_context = self._format_results(results, keywords)

        # Build message with context
        full_message = user_message
        if search_context:
            full_message = f"{user_message}\n\n[Produits trouvés dans la base Amazon]\n{search_context}"
        elif keywords:
            full_message = f"{user_message}\n\n[Aucun produit trouvé pour '{keywords}' dans la base]"

        self._conversations[user_id].append({"role": "user", "content": full_message})

        # Keep last 16 messages
        if len(self._conversations[user_id]) > 16:
            self._conversations[user_id] = self._conversations[user_id][-16:]

        response = self.client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=1200,
            temperature=0.4,  # Plus précis, moins créatif
            messages=[
                {"role": "system", "content": self._system_prompt(user_id)},
                *self._conversations[user_id],
            ],
        )

        reply = response.choices[0].message.content
        self._conversations[user_id].append({"role": "assistant", "content": reply})

        # Save to DB
        if keywords:
            self.db.save_search(user_id, keywords)
        self._update_preferences(user_id, user_message, budget)

        return reply

    # ── Helpers ────────────────────────────────

    def _format_results(self, results: List[Dict], query: str) -> str:
        if not results:
            return f"Aucun produit trouvé pour '{query}'"

        lines = []
        for p in results:
            line = f"- {p['name'][:100]}"
            if p.get("price_display"):
                line += f" | Prix: {p['price_display']}"
            if p.get("list_price_display"):
                line += f" (original: {p['list_price_display']}, {p.get('discount_display', '')})"
            if p.get("stars"):
                line += f" | ⭐{p['stars']}"
            if p.get("reviews"):
                line += f" ({p['reviews']:,} avis)"
            if p.get("is_best_seller"):
                line += " | 🏆 Best Seller"
            if p.get("bought_last_month"):
                line += f" | {p['bought_last_month']:,} achetés ce mois"
            if p.get("category_name"):
                line += f" | Catégorie: {p['category_name']}"
            if p.get("url"):
                line += f"\n  URL: {p['url']}"
            lines.append(line)

        return "\n".join(lines)

    def _extract_budget(self, message: str) -> Optional[float]:
        patterns = [
            r"sous\s*(\d+)\s*[€$]",
            r"moins\s*de\s*(\d+)\s*[€$]",
            r"max\w*\s*(\d+)\s*[€$]",
            r"(\d+)\s*[€$]\s*max",
            r"under\s*\$?(\d+)",
            r"less\s*than\s*\$?(\d+)",
            r"budget\s*[:\s]*(\d+)",
            r"(\d+)\s*[€$]",
        ]
        for pattern in patterns:
            match = re.search(pattern, message.lower())
            if match:
                return float(match.group(1))
        return None

    def _extract_keywords(self, message: str) -> str:
        stop_words = {
            "je", "cherche", "veux", "voudrais", "un", "une", "des", "le", "la", "les",
            "pour", "avec", "sous", "dans", "sur", "mon", "ma", "mes", "cadeau",
            "acheter", "trouver", "bon", "bonne", "meilleur", "meilleure", "propose",
            "i", "want", "need", "looking", "for", "a", "the", "best", "good", "find",
            "show", "give", "recommend", "suggestion", "please", "can", "you",
            "max", "budget", "moins", "plus", "cher", "pas"
        }
        words = [
            w.strip("?!.,()") for w in message.lower().split()
            if w.strip("?!.,()") not in stop_words
            and len(w.strip("?!.,()")) > 2
            and not re.match(r"^\d+[€$]?$", w)
        ]
        return " ".join(words[:5])

    def _update_preferences(self, user_id: int, message: str, budget: Optional[float]):
        prefs = self.db.get_user_preferences(user_id) or {}

        if budget:
            prefs["budget"] = f"{budget:.0f}€"

        categories = {
            "audio": ["casque", "écouteur", "headphone", "speaker", "microphone", "airpods"],
            "informatique": ["laptop", "pc", "ordinateur", "clavier", "souris", "cable", "monitor"],
            "téléphonie": ["iphone", "samsung", "téléphone", "smartphone", "android", "phone"],
            "sport": ["sport", "fitness", "running", "gym", "vélo", "yoga"],
            "maison": ["maison", "cuisine", "décoration", "aspirateur", "kitchen"],
            "gaming": ["gaming", "game", "ps5", "xbox", "nintendo", "manette"],
        }
        msg_lower = message.lower()
        fav = prefs.get("favorite_categories", [])
        for cat, kws in categories.items():
            if any(kw in msg_lower for kw in kws) and cat not in fav:
                fav.append(cat)
        prefs["favorite_categories"] = fav[-5:]

        if prefs:
            self.db.save_user_preferences(user_id, prefs)

    def clear_memory(self, user_id: int):
        self._conversations.pop(user_id, None)

    def get_conversation_length(self, user_id: int) -> int:
        return len(self._conversations.get(user_id, []))
