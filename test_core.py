import tempfile
from pathlib import Path

from database import OrderDatabase
from gemini_ai import GeminiOrderAI
from order_manager import OrderManager


def run():
    with tempfile.TemporaryDirectory() as tmp:
        db = OrderDatabase(str(Path(tmp) / "orders.db"))
        manager = OrderManager(db)
        ai = GeminiOrderAI(None)
        scope = "group:test"

        manager.start_new_round(scope)

        first = ai.parse_chat(
            "豬腳飯 100\n辣腿排飯 95\n炒麻油雞飯 95",
            "Wu Yi Ru", [], {}, None
        )
        assert first["action"] == "add", first
        assert manager.apply_ai_result(scope, "u1", "Wu Yi Ru", first)

        second = ai.parse_chat(
            "招牌飯90，雞腿飯105x2=210，鮭魚飯105，共405，謝謝",
            "Wu Yi Ru", [], manager.public_orders(scope), "Wu Yi Ru"
        )
        assert second["action"] == "add", second
        assert manager.apply_ai_result(scope, "u1", "Wu Yi Ru", second)

        summary = manager.summary(scope)
        expected = [
            "豬腳飯 1",
            "辣腿排飯 1",
            "炒麻油雞飯 1",
            "招牌飯 1",
            "雞腿飯 2",
            "鮭魚飯 1",
        ]
        for line in expected:
            assert line in summary, (line, summary)

        ignored = ai.parse_chat("共400，謝謝", "Wu Yi Ru", [], {}, None)
        assert ignored["action"] == "ignore", ignored

        changed = ai.parse_chat("改成排骨飯", "Wu Yi Ru", [], {}, None)
        assert changed["action"] == "set", changed


        # 「+」連接的餐點必須拆開計算
        plus_order = ai.parse_chat(
            "炒麵小+隔間肉湯=100謝謝",
            "Wu Yi Ru", [], {}, None
        )
        assert plus_order == {
            "action": "add",
            "items": [
                {"name": "炒麵小", "qty": 1},
                {"name": "隔間肉湯", "qty": 1},
            ],
        }, plus_order

        fullwidth_plus_order = ai.parse_chat(
            "炒麵 大 ＋ 荷包蛋",
            "Wu Yi Ru", [], {}, None
        )
        assert fullwidth_plus_order == {
            "action": "add",
            "items": [
                {"name": "炒麵 大", "qty": 1},
                {"name": "荷包蛋", "qty": 1},
            ],
        }, fullwidth_plus_order

        ampersand_order = ai.parse_chat(
            "雞腿飯&滷蛋&豆干",
            "Wu Yi Ru", [], {}, None
        )
        assert ampersand_order == {
            "action": "add",
            "items": [
                {"name": "雞腿飯", "qty": 1},
                {"name": "滷蛋", "qty": 1},
                {"name": "豆干", "qty": 1},
            ],
        }, ampersand_order

        # A-Z / Unicode 排序
        manager.clear(scope)
        manager.apply_ai_result(
            scope, "u1", "Wu Yi Ru",
            {"action": "add", "items": [
                {"name": "糖醋里肌 飯半", "qty": 1},
                {"name": "卡拉雞排", "qty": 1},
                {"name": "糖醋里肌", "qty": 5},
                {"name": "塔香三杯雞", "qty": 1},
            ]}
        )
        sorted_summary = manager.summary(scope)
        ordered_lines = [
            "卡拉雞排 1",
            "塔香三杯雞 1",
            "糖醋里肌 5",
            "糖醋里肌 飯半 1",
        ]
        positions = [sorted_summary.index(line) for line in ordered_lines]
        assert positions == sorted(positions), sorted_summary

        print("All core tests passed.")
        print(summary)


if __name__ == "__main__":
    run()
