import aiohttp
import asyncio
from typing import Optional

BASE_URL = "https://localhost:8000"

class EconomyAPI:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def get_user(self, shared_id: str) -> Optional[dict]:
        try:
            async with self.session.get(f"{BASE_URL}/user/{shared_id}") as resp:
                if resp.status == 200:
                    return await resp.json()
                print(f"[get_user] Error {resp.status}: {await resp.text()}")
        except aiohttp.ClientError as e:
            print(f"[get_user] ClientError: {e}")
        return None

    async def create_user(self, shared_id: str) -> Optional[dict]:
        try:
            async with self.session.post(f"{BASE_URL}/user", json={"shared_id": shared_id}) as resp:
                if resp.status == 200 or resp.status == 201:
                    return await resp.json()
                print(f"[create_user] Error {resp.status}: {await resp.text()}")
        except aiohttp.ClientError as e:
            print(f"[create_user] ClientError: {e}")
        return None

    async def update_user(self, shared_id: str, data: dict) -> Optional[dict]:
        try:
            async with self.session.patch(f"{BASE_URL}/user/{shared_id}", json=data) as resp:
                if resp.status == 200:
                    return await resp.json()
                print(f"[update_user] Error {resp.status}: {await resp.text()}")
        except aiohttp.ClientError as e:
            print(f"[update_user] ClientError: {e}")
        return None
    async def get_all_user(self) -> Optional[list]:
        try:
            async with self.session.get(f"{BASE_URL}/user") as resp:
                if resp.status == 200:
                    return await resp.json()
                print(f"[get_all_user] Error {resp.status}: {await resp.text()}")
        except aiohttp.ClientError as e:
            print(f"[get_all_user] ClientError: {e}")
        return None