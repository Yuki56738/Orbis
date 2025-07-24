import aiohttp
from typing import Optional, List

BASE_URL = "https://localhost:8000"  # 適宜変更してください

class ItemAPI:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def get_items(self, gov_id: str) -> Optional[List[dict]]:
        try:
            async with self.session.get(f"{BASE_URL}/items/{gov_id}") as resp:
                if resp.status == 200:
                    return await resp.json()
                print(f"[get_items] Error {resp.status}: {await resp.text()}")
        except aiohttp.ClientError as e:
            print(f"[get_items] ClientError: {e}")
        return None

    async def add_item(self, gov_id: str, item_id: str, amount: int = 1) -> Optional[dict]:
        try:
            payload = {
                "gov_id": gov_id,
                "item_id": item_id,
                "amount": amount
            }
            async with self.session.put(f"{BASE_URL}/items/add", json=payload) as resp:
                if resp.status in (200, 201):
                    return await resp.json()
                print(f"[add_item] Error {resp.status}: {await resp.text()}")
        except aiohttp.ClientError as e:
            print(f"[add_item] ClientError: {e}")
        return None

    async def update_item_amount(self, inventory_id: str, amount: int) -> Optional[dict]:
        try:
            payload = {
                "inventory_id": inventory_id,
                "amount": amount
            }
            async with self.session.post(f"{BASE_URL}/items/update", json=payload) as resp:
                if resp.status == 200:
                    return await resp.json()
                print(f"[update_item_amount] Error {resp.status}: {await resp.text()}")
        except aiohttp.ClientError as e:
            print(f"[update_item_amount] ClientError: {e}")
        return None

    async def delete_item(self, inventory_id: str) -> bool:
        try:
            async with self.session.delete(f"{BASE_URL}/items/{inventory_id}") as resp:
                if resp.status == 200:
                    return True
                print(f"[delete_item] Error {resp.status}: {await resp.text()}")
        except aiohttp.ClientError as e:
            print(f"[delete_item] ClientError: {e}")
        return False

# ここから追加ユーティリティ関数

async def consume_item(gov_id: str, item_id: str) -> bool:
    """
    アイテムを1個消費する処理
    所持していればamountを-1し、0になればアイテム削除
    成功すればTrue, 所持なしはFalse返す
    """
    async with aiohttp.ClientSession() as session:
        api = ItemAPI(session)
        items = await api.get_items(gov_id)
        if not items:
            return False
        # 対象アイテムを探す
        for item in items:
            if item.get("item_id") == item_id and item.get("amount", 0) > 0:
                inventory_id = item.get("inventory_id")
                new_amount = item["amount"] - 1
                if new_amount > 0:
                    updated = await api.update_item_amount(inventory_id, new_amount)
                    return updated is not None
                else:
                    deleted = await api.delete_item(inventory_id)
                    return deleted
        return False
