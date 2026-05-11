import os
from dotenv import load_dotenv
load_dotenv()

class Config:
    BOT_TOKEN: str       = os.getenv("BOT_TOKEN", "")
    GROQ_API_KEY: str    = os.getenv("GROQ_API_KEY", "")
    ADMIN_IDS: list      = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]
    DB_PATH: str         = os.getenv("DB_PATH", "shopping_bot.db")
    PRODUCTS_DB: str     = os.getenv("PRODUCTS_DB", "products.db")
    CSV_PATH: str        = os.getenv("CSV_PATH", "data/amazon_products.csv")
    MAX_RESULTS: int     = int(os.getenv("MAX_RESULTS", "5"))

    @classmethod
    def validate(cls):
        missing = [k for k, v in [("BOT_TOKEN", cls.BOT_TOKEN), ("GROQ_API_KEY", cls.GROQ_API_KEY)] if not v]
        if missing:
            raise ValueError(f"❌ Variables manquantes dans .env : {', '.join(missing)}")
