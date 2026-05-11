"""
bot_ai_improved.py - Bot avec meilleure compréhension naturelle
Renomme en bot.py
"""

import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
import os
from dotenv import load_dotenv
import re
from datetime import datetime
from collections import defaultdict

# Imports locaux
try:
    from price_finder import PriceFinder
    from database import Database
except ImportError as e:
    print(f"❌ Erreur import: {e}")
    exit(1)

# Configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not TELEGRAM_TOKEN or not GROQ_API_KEY:
    raise ValueError("❌ TELEGRAM_TOKEN ou GROQ_API_KEY manquant dans .env")

# ═══════════════════════════════════════════════════════════════
# GROQ CLIENT AVEC MEILLEURE IA
# ═══════════════════════════════════════════════════════════════

try:
    from groq import Groq
    groq_client = Groq(api_key=GROQ_API_KEY)
except:
    logger.warning("⚠️ Groq SDK pas installé")
    groq_client = None


def generate_smart_response(user_message: str, product_results: list = None, context: str = "") -> str:
    """
    Génère une réponse intelligente avec Groq
    Comprend mieux les questions naturelles
    """
    
    if not groq_client:
        if product_results:
            return f"✅ {len(product_results)} produit(s) trouvé(s)"
        else:
            return "Pas de résultats. Essaie un autre terme!"
    
    # Construit le prompt pour Groq
    if product_results:
        # L'utilisateur a une liste de produits à commenter
        products_text = "\n".join([
            f"• {p['name'][:60]}: ${p.get('price', 'N/A')} (⭐{p.get('stars', 'N/A')}/5, {p.get('reviews', 0):,} avis)"
            for p in product_results[:5]
        ])
        
        system_prompt = """Tu es un assistant shopping Amazon très amical et utile.
L'utilisateur a cherché des produits et tu dois:
1. Valider que les résultats match la recherche
2. Donner un avis court et utile (1-2 phrases MAX)
3. Recommander un produit si possible
4. Garder un ton conversationnel et naturel

Sois bref, utile, pas de blabla inutile."""

        user_prompt = f"""L'utilisateur a cherché: "{user_message}"

Voici les produits trouvés:
{products_text}

Donne un court commentaire (MAX 2 phrases). Recommande le meilleur si possible."""

    else:
        # L'utilisateur a posé une question ou cherche quelque chose qu'on n'a pas trouvé
        system_prompt = """Tu es un assistant shopping Amazon très amical.
L'utilisateur pose une question ou cherche quelque chose.
- Si c'est une question sur Amazon/shopping: réponds utilement et brièvement
- Si c'est une recherche produit: donne des suggestions
- Sois naturel, conversationnel, court (MAX 2-3 phrases)"""

        user_prompt = f"L'utilisateur: {user_message}\n\nRéponds brièvement et utilement."
    
    try:
        message = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            model="llama-3.1-8b-instant",
            max_tokens=200,
            temperature=0.7,
        )
        response = message.choices[0].message.content.strip()
        
        # Assure que c'est pas trop long
        if len(response) > 500:
            response = response[:500] + "..."
        
        return response
        
    except Exception as e:
        logger.error(f"Groq error: {e}")
        if product_results:
            return "✅ Produits trouvés! Clique sur les liens pour plus d'infos."
        else:
            return "Hmm, je n'ai pas trouvé ça. Essaie un terme différent!"


# ═══════════════════════════════════════════════════════════════
# RECONNAISSANCE D'INTENTIONS - Comprendre ce que veut l'utilisateur
# ═══════════════════════════════════════════════════════════════

def detect_intent(message: str) -> dict:
    """
    Détecte l'intention de l'utilisateur
    Retourne: {type: 'search'|'question'|'greeting', query: str, max_price: float|None}
    """
    
    message_lower = message.lower().strip()
    
    # Salutations
    greetings = ['bonjour', 'hi', 'hello', 'salut', 'coucou', 'yo', 'ça va', 'comment ça va']
    if any(g in message_lower for g in greetings):
        return {'type': 'greeting', 'query': message}
    
    # Questions
    question_words = ['quoi', 'quel', 'pourquoi', 'comment', 'où', 'combien', 'est-ce que', 'can you', 'what', 'how', 'which']
    if any(q in message_lower for q in question_words):
        return {'type': 'question', 'query': message}
    
    # Recherche produit
    # Parse le message pour chercher un prix max
    max_price = None
    query = message
    
    price_patterns = [
        r'max[:\s]+\$?(\d+)',
        r'max\s+(\d+)',
        r'moins\s+de\s+\$?(\d+)',
        r'under\s+\$?(\d+)',
        r'\$?(\d+)\s+(max|ou moins)',
    ]
    
    for pattern in price_patterns:
        match = re.search(pattern, message_lower)
        if match:
            max_price = float(match.group(1))
            query = re.sub(pattern, '', message, flags=re.IGNORECASE).strip()
            break
    
    return {
        'type': 'search',
        'query': query if query else message,
        'max_price': max_price
    }


def format_products_nicely(results: list) -> str:
    """Formate les produits de manière lisible"""
    if not results:
        return "Aucun produit trouvé"
    
    message = f"✅ {len(results)} produit(s) trouvé(s):\n\n"
    
    for i, p in enumerate(results, 1):
        name = p.get('name', 'N/A')[:70]
        price = p.get('price_display', 'N/A')
        stars = p.get('stars', 'N/A')
        reviews = p.get('reviews', 0)
        discount = p.get('discount_display', '')
        url = p.get('url', '')
        
        message += f"{i}. {name}\n"
        message += f"   💰 {price}"
        
        if discount:
            message += f" {discount}"
        message += "\n"
        
        if stars and stars != 'N/A':
            message += f"   ⭐ {stars}/5 ({reviews:,} avis)\n"
        
        if url:
            message += f"   🔗 {url[:55]}...\n"
        
        message += "\n"
    
    return message.strip()


def clean_message(text: str, max_length: int = 4096) -> str:
    """Nettoie le texte pour Telegram"""
    if not text:
        return "No response"
    
    text = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', text)
    
    if len(text) > max_length:
        text = text[:max_length-20] + "\n...(message trop long)"
    
    return text


# ═══════════════════════════════════════════════════════════════
# HANDLERS TELEGRAM
# ═══════════════════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /start"""
    user = update.message.from_user
    user_id = user.id
    
    db = Database()
    db.save_user(user_id, user.username, user.first_name)
    
    welcome = f"""🤖 Salut {user.first_name}! 👋

Je suis ton bot Amazon qui trouve des produits pour toi!

📝 Comment m'utiliser:
• Envoie simplement un produit: "shirt", "laptop"
• Je te montre les meilleurs avec prix & avis
• Pose-moi des questions naturelles!

💡 Exemples:
✍️ "shirt blanc homme"
✍️ "laptop gaming max:1000"
✍️ "trouvez moi des chaussures de running"
✍️ "c'est quoi les meilleures chaussures?"

Commandes:
/help - Aide détaillée
/categories - Catégories disponibles
/stats - Tes stats

C'est parti! 🚀"""
    
    await update.message.reply_text(
        clean_message(welcome),
        parse_mode=None
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère les messages - Version intelligente"""
    
    user_message = update.message.text.strip()
    user_id = update.message.from_user.id
    
    if not user_message or len(user_message) < 2:
        return
    
    # Show typing
    await update.message.chat.send_action("typing")
    
    db = Database()
    finder = PriceFinder("products.db")
    
    try:
        # Sauvegarde l'utilisateur
        user = update.message.from_user
        db.save_user(user_id, user.username, user.first_name)
        
        # Détecte l'intention
        intent = detect_intent(user_message)
        intent_type = intent['type']
        
        logger.info(f"[USER {user_id}] Intent: {intent_type}, Message: {user_message[:50]}")
        
        # ════════════════════════════════════════════════
        # 1. SALUTATION
        # ════════════════════════════════════════════════
        if intent_type == 'greeting':
            response = "Salut! 👋 Qu'est-ce que je peux t'aider à trouver? Des vêtements? De l'électronique? 😊"
            await update.message.reply_text(
                clean_message(response),
                parse_mode=None
            )
            return
        
        # ════════════════════════════════════════════════
        # 2. QUESTION GÉNÉRALE
        # ════════════════════════════════════════════════
        if intent_type == 'question':
            # Pour les questions générales, utilise Groq
            ai_response = generate_smart_response(user_message)
            
            response = ai_response
            
            # Ajoute une suggestion si c'est une question sur des produits
            if any(word in user_message.lower() for word in ['meilleur', 'best', 'quel', 'which', 'recommande', 'suggest']):
                response += "\n\n💡 Ou tu peux chercher directement: 'shirt', 'laptop', 'shoes'..."
            
            await update.message.reply_text(
                clean_message(response),
                parse_mode=None
            )
            
            db.save_search(user_id, user_message, None)
            return
        
        # ════════════════════════════════════════════════
        # 3. RECHERCHE PRODUIT
        # ════════════════════════════════════════════════
        if intent_type == 'search':
            query = intent['query']
            max_price = intent['max_price']
            
            logger.info(f"   Searching: '{query}' (max: ${max_price if max_price else 'any'})")
            
            # Cherche les produits
            results = finder.search(
                query,
                max_results=5,
                max_price=max_price
            )
            
            # Formate les résultats
            products_message = format_products_nicely(results)
            
            # Génère commentaire IA
            ai_comment = generate_smart_response(
                user_message,
                results if results else None
            )
            
            # Combine tout
            response = products_message + "\n\n" + ai_comment
            
            await update.message.reply_text(
                clean_message(response),
                parse_mode=None
            )
            
            # Sauvegarde la recherche
            if results:
                db.save_search(user_id, user_message, [
                    {k: v for k, v in r.items() if k != '_score'}
                    for r in results
                ])
            else:
                db.save_search(user_id, user_message, None)
            
            return
    
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        
        error_msg = f"Oops! Une petite erreur: {str(e)[:100]}"
        try:
            await update.message.reply_text(
                clean_message(error_msg),
                parse_mode=None
            )
        except:
            await update.message.reply_text("Error")


async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /help"""
    help_text = """📚 COMMENT M'UTILISER

🔍 CHERCHER DES PRODUITS:
Envoie simplement ce que tu cherches:
• "shirt blanc" 
• "gaming laptop"
• "chaussures de running"

💰 FILTRER PAR PRIX:
• "laptop max:1000"
• "shoes moins de 100"
• "shirts under 50"

❓ POSER DES QUESTIONS:
Je peux répondre à tes questions:
• "Quelles sont les meilleures chaussures?"
• "Quel laptop recommandes-tu?"
• "Où trouver des shirts de qualité?"

📂 VOIR LES CATÉGORIES:
/categories - Voir les catégories disponibles
/stats - Tes statistiques de recherche

💡 TIP:
- Sois spécifique ("shirt coton bleu" vs juste "shirt")
- Je comprends le français et l'anglais
- Prix en USD
- On a 500K+ produits Amazon!
"""
    
    await update.message.reply_text(
        clean_message(help_text),
        parse_mode=None
    )


async def handle_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche catégories"""
    finder = PriceFinder("products.db")
    
    try:
        categories = finder.get_popular_categories(limit=12)
        
        if not categories:
            await update.message.reply_text("Pas de catégories", parse_mode=None)
            return
        
        message = "📂 CATÉGORIES DISPONIBLES:\n\n"
        for cat, count in categories:
            message += f"• {cat}: {count:,}\n"
        
        message += "\n🔍 Cherche: /search clothing\nOu envoie: \"shirt bleu\""
        
        await update.message.reply_text(
            clean_message(message),
            parse_mode=None
        )
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("Erreur", parse_mode=None)


async def handle_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stats utilisateur"""
    user_id = update.message.from_user.id
    db = Database()
    
    try:
        stats = db.get_user_stats(user_id)
        
        message = f"""📊 TES STATS

🔍 Recherches: {stats['total_searches']}
🎯 Produits uniques: {stats['unique_products']}
📅 Membre depuis: {stats['member_since']}
"""
        
        await update.message.reply_text(
            clean_message(message),
            parse_mode=None
        )
    except Exception as e:
        logger.error(f"Error: {e}")


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    """Lance le bot"""
    
    db = Database()
    finder = PriceFinder("products.db")
    count = finder.get_product_count()
    
    logger.info("✅ Database initialisée")
    logger.info(f"✅ {count:,} produits disponibles")
    
    if count == 0:
        logger.warning("⚠️ BD produits vide! Exécute: python load_data.py")
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Commandes
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", handle_help))
    app.add_handler(CommandHandler("categories", handle_categories))
    app.add_handler(CommandHandler("stats", handle_stats))
    
    # Messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🤖 Bot LANCÉ - En attente de messages...")
    logger.info(f"Token: {TELEGRAM_TOKEN[:20]}...")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
