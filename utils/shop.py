import aiohttp
import logging
import json
from pathlib import Path

BASE_URL = "http://localhost:8000/api/shop"  # 仮のAPIエンドポイント
logger = logging.getLogger(__name__)

# JSON定義ファイルのパス（Botが販売する公式アイテム定義）
DATA_DIR = Path(__file__).parent.parent / "data"
ITEM_DEF_FILE = DATA_DIR / "items_definition.json"

# 一度だけ読み込むようにキャッシュ
_item_definitions: dict[str, dict] = {}


def load_item_definitions() -> dict[str, dict]:
    """Bot公式が販売するアイテム定義（JSONから読み込み）"""
    global _item_definitions
    if not _item_definitions:
        try:
            with open(ITEM_DEF_FILE, "r", encoding="utf-8") as f:
                _item_definitions = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load item definitions from JSON: {e}")
            _item_definitions = {}
    return _item_definitions


def get_item_definition(item_id: str) -> dict | None:
    """指定アイテムの定義を返す"""
    definitions = load_item_definitions()
    return definitions.get(item_id)


async def fetch_shop_items() -> list[dict]:
    """現在販売中のショップアイテムリスト（API + JSON連携）"""
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BASE_URL}/items") as resp:
            if resp.status == 200:
                db_items = await resp.json()
                full_items = []
                for item in db_items:
                    item_id = item.get("item_id")
                    item_def = get_item_definition(item_id)
                    if not item_def:
                        continue  # 定義されていないアイテムは除外
                    # DB + JSONマージ
                    full_items.append({
                        "shop_item_id": item["shop_item_id"],
                        "item_id": item_id,
                        "name": item_def["name"],
                        "description": item_def["description"],
                        "price": item["price"],
                        "stock": item["stock"],
                        "daily_reset": item["daily_reset"],
                        "max_daily_stock": item["max_daily_stock"],
                        "max_own": item_def["max_own"],
                        "weekly_limit": item_def["weekly_limit"],
                        "daily_limit": item_def["daily_limit"],
                        "active": item["active"]
                    })
                return full_items
            logger.error(f"Failed to fetch shop items. Status: {resp.status}")
            return []


async def fetch_item_stock(item_id: str) -> int:
    """指定アイテムの在庫数を取得（DB依存）"""
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BASE_URL}/items/{item_id}") as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("stock", 0)
            logger.error(f"Failed to fetch stock for {item_id}. Status: {resp.status}")
            return 0


async def purchase_item(gov_id: str, item_id: str, amount: int = 1) -> bool:
    """購入処理：在庫を減らす + 経済DBと連携"""
    payload = {
        "gov_id": gov_id,
        "item_id": item_id,
        "amount": amount
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{BASE_URL}/buy", json=payload) as resp:
            if resp.status == 200:
                return True
            logger.error(f"Failed to purchase {item_id} x{amount} for {gov_id}. Status: {resp.status}")
            return False


async def restock_item(item_id: str, amount: int) -> bool:
    """管理者用：在庫を追加"""
    payload = {
        "item_id": item_id,
        "amount": amount,
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{BASE_URL}/restock", json=payload) as resp:
            if resp.status == 200:
                return True
            logger.error(f"Failed to restock {item_id}. Status: {resp.status}")
            return False


async def reset_daily_stock() -> bool:
    """毎日の在庫リセット"""
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{BASE_URL}/reset") as resp:
            if resp.status == 200:
                return True
            logger.error("Failed to reset daily shop stock.")
            return False
