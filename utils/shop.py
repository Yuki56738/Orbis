import aiohttp
import logging

BASE_URL = "http://localhost:8000/api/shop"  # 仮のURL
logger = logging.getLogger(__name__)


async def fetch_shop_items() -> list[dict]:
    """ショップに並んでいるすべてのアイテムを取得"""
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BASE_URL}/items") as resp:
            if resp.status == 200:
                return await resp.json()
            logger.error(f"Failed to fetch shop items. Status: {resp.status}")
            return []


async def fetch_item_stock(item_id: str) -> int:
    """特定のアイテムの在庫数を取得"""
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BASE_URL}/items/{item_id}") as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("stock", 0)
            logger.error(f"Failed to fetch stock for {item_id}. Status: {resp.status}")
            return 0


async def purchase_item(gov_id: str, item_id: str, amount: int = 1) -> bool:
    """アイテムを購入（在庫減少）"""
    payload = {
        "gov_id": gov_id,
        "item_id": item_id,
        "amount": amount,
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{BASE_URL}/buy", json=payload) as resp:
            if resp.status == 200:
                return True
            logger.error(f"Failed to purchase {item_id} x{amount} for {gov_id}. Status: {resp.status}")
            return False


async def restock_item(item_id: str, amount: int) -> bool:
    """Botが管理するアイテムの在庫を追加"""
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
    """1日1回在庫を全体リセット"""
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{BASE_URL}/reset") as resp:
            if resp.status == 200:
                return True
            logger.error("Failed to reset daily shop stock.")
            return False
