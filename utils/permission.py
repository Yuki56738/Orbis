import json

def is_event_admin(user_id: int) -> bool:
    try:
        with open('data/event_admin.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            return user_id in data.get("admin_ids", [])
    except Exception as e:
        print(f"[ERROR] event_admin.json の読み込みに失敗しました: {e}")
        return False