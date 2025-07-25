import json
import random
import datetime
import os

FORTUNE_FILE = "data/fortune_effects.json"
USER_FORTUNE_FILE = "data/user_fortunes.json"

async def load_fortune_data():
    with open(FORTUNE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

async def get_today_fortune(user_id: int) -> dict:
    today_str = datetime.date.today().isoformat()
    if os.path.exists(USER_FORTUNE_FILE):
        with open(USER_FORTUNE_FILE, "r", encoding="utf-8") as f:
            user_fortunes = json.load(f)
    else:
        user_fortunes = {}

    key = str(user_id)
    if key in user_fortunes and user_fortunes[key]["date"] == today_str:
        return user_fortunes[key]

    all_fortunes = await load_fortune_data()
    chosen = random.choice(all_fortunes)
    user_fortunes[key] = {"date": today_str, "fortune": chosen}
    with open(USER_FORTUNE_FILE, "w", encoding="utf-8") as f:
        json.dump(user_fortunes, f, ensure_ascii=False, indent=2)
    return user_fortunes[key]

async def get_today_fortune_effects(user_id: int) -> dict:
    data = await get_today_fortune(user_id)
    return data["fortune"].get("effects", {})
