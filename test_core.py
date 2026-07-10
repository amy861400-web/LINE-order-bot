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

        # 相同主餐的不同備註要相鄰顯示
        manager.clear(scope)
        manager.apply_ai_result(
            scope, "u1", "Wu Yi Ru",
            {"action": "add", "items": [
                {"name": "卡拉雞排", "qty": 1},
                {"name": "糖醋里肌 飯半", "qty": 1},
                {"name": "塔香三杯雞", "qty": 1},
                {"name": "糖醋里肌", "qty": 5},
            ]}
        )
        grouped_summary = manager.summary(scope)
        first = grouped_summary.index("糖醋里肌 5")
        second = grouped_summary.index("糖醋里肌 飯半 1")
        assert first < second
        between = grouped_summary[first:second]
        assert "塔香三杯雞" not in between

        print("All core tests passed.")
        print(summary)


if __name__ == "__main__":
    run()
