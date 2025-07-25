import random
import json
import os
from typing import Optional
import aiohttp

from utils import economy_api
from utils import item as item_utils

DATA_DIR = os.path.join(os.path.dirname(__file__), "../data")

def load_json(filename: str):
    with open(os.path.join(DATA_DIR, filename), encoding="utf-8") as f:
        return json.load(f)

ADVENTURE_STAGES = load_json("adventure_stages.json")
ADVENTURE_EVENTS = load_json("adventure_events.json")
STATUS_CHECK_TYPES = load_json("status_check_types.json")
ADVENTURE_REWARDS = load_json("adventure_rewards.json")

def roll_dice(num_dice: int = 1, sides: int = 20) -> int:
    return sum(random.randint(1, sides) for _ in range(num_dice))

def check_success(dice_roll: int, stat_value: int, dc: int) -> bool:
    return (dice_roll + stat_value) >= dc

class AdventureManager:
    def __init__(self, userdb_handler):
        self.userdb = userdb_handler

    async def get_stat(self, user_id: int, stat_id: str) -> int:
        val = await self.userdb.get_user_setting(user_id, f"stat_{stat_id}")
        return int(val) if val and val.isdigit() else 10  # デフォルト10

    async def start_adventure(self, user_id: int, stage_id: str, difficulty: str) -> dict:
        stage = next((s for s in ADVENTURE_STAGES if s["id"] == stage_id), None)
        if not stage:
            raise ValueError("無効なステージIDです。")
        if difficulty not in stage["difficulty_levels"]:
            raise ValueError("無効な難易度です。")

        max_turns = stage["max_turns"]
        base_hp = 100

        state = {
            "stage_id": stage_id,
            "difficulty": difficulty,
            "turn": 1,
            "max_turns": max_turns,
            "hp": base_hp,
            "max_hp": base_hp,
            "exp": 0,
            "gold": 0,
            "inventory": {},
            "log": [f"冒険『{stage['name']}』を開始しました。難易度: {difficulty}"]
        }

        await self.userdb.set_adventure_state(user_id, state)
        return state

    async def get_state(self, user_id: int) -> Optional[dict]:
        return await self.userdb.get_adventure_state(user_id)

    async def clear_state(self, user_id: int):
        await self.userdb.clear_adventure_state(user_id)

    async def explore(self, user_id: int, selected_option: Optional[int] = None) -> dict:
        state = await self.get_state(user_id)
        if not state:
            raise ValueError("冒険が開始されていません。")
        if state["turn"] > state["max_turns"]:
            raise ValueError("冒険が終了しています。")

        event = random.choice(ADVENTURE_EVENTS)
        check_type = event.get("check_type", "luk")
        stat_value = await self.get_stat(user_id, check_type)
        dice = roll_dice()
        success = check_success(dice, stat_value, event["difficulty_class"])

        if success:
            msg = event.get("success_message", "成功しました。")
            if event.get("reward"):
                for k, v in event["reward"].items():
                    if k == "gold":
                        state["gold"] += v
        else:
            msg = event.get("failure_message", "失敗しました。")
            if event.get("damage"):
                state["hp"] = max(0, state["hp"] - event["damage"])

        state["log"].append(f"Turn {state['turn']}: {event['description']} → {msg}")
        state["turn"] += 1

        await self.userdb.set_adventure_state(user_id, state)

        return {
            "state": state,
            "event": event,
            "success": success,
            "dice": dice,
            "stat_value": stat_value,
            "message": msg,
        }

    async def end_adventure(self, user_id: int, session: aiohttp.ClientSession) -> dict:
        state = await self.get_state(user_id)
        if not state:
            raise ValueError("冒険が開始されていません。")

        base_exp = random.randint(
            ADVENTURE_REWARDS["base_rewards"]["exp"]["min"],
            ADVENTURE_REWARDS["base_rewards"]["exp"]["max"],
        )
        base_gold = random.randint(
            ADVENTURE_REWARDS["base_rewards"]["gold"]["min"],
            ADVENTURE_REWARDS["base_rewards"]["gold"]["max"],
        )

        # アイテム報酬
        for item_reward in ADVENTURE_REWARDS["item_rewards"]:
            if random.random() <= item_reward["chance"]:
                item_id = item_reward["item_id"]
                state["inventory"][item_id] = state["inventory"].get(item_id, 0) + 1

        # 経験値保存（既存分に加算）
        prev_exp = await self.userdb.get_user_setting(user_id, "exp")
        total_exp = base_exp + (int(prev_exp) if prev_exp and prev_exp.isdigit() else 0)
        await self.userdb.set_user_setting(user_id, "exp", str(total_exp))

        # ゴールド加算（外部API）
        economy = economy_api.EconomyAPI(session)
        await economy.update_user(str(user_id), {"gold": base_gold})

        # アイテム付与（外部API）
        for item_id, count in state["inventory"].items():
            await item_utils.ItemAPI(session).add_item(str(user_id), item_id, count)

        await self.userdb.clear_adventure_state(user_id)

        return {
            "exp": base_exp,
            "gold": base_gold,
            "items": list(state["inventory"].keys()),
            "log": state["log"]
        }
