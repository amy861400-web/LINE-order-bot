import tempfile
from pathlib import Path
from database import OrderDatabase
from order_manager import OrderManager
from parser import OrderParser

def run():
    with tempfile.TemporaryDirectory() as t:
        path=str(Path(t)/"orders.db");p=OrderParser();s="group:test"
        m=OrderManager(OrderDatabase(path))
        # 沒先傳圖片也會自動建立 Round
        r=p.parse("炒麵大x3=150");assert r=={"action":"add","items":[{"name":"炒麵 大","qty":3}]},r;assert m.apply(s,"u1","Wu Yi Ru",r)
        for msg in ["綜合湯X3=180","雞腿飯×2=210","滷蛋 * 4 = 60","炒麵小+隔間肉湯=100謝謝","炒麵 大 +荷包蛋"]:
            r=p.parse(msg);assert r["action"]=="add",r;assert m.apply(s,"u1","Wu Yi Ru",r)
        # 模擬重啟後仍讀得到同一輪
        m2=OrderManager(OrderDatabase(path));summary=m2.summary(s)
        for line in ["炒麵 大 4","炒麵 小 1","綜合湯 3","雞腿飯 2","滷蛋 4","隔間肉湯 1","荷包蛋 1","本輪共 1 人","共 16 份"]:assert line in summary,(line,summary)
        st=m2.status(s);assert "Version：2.1 LTS" in st and "Status：OPEN" in st and "People：1" in st and "Orders：16" in st,st
        # 新圖片建立新輪
        m2.start_new_round(s);assert m2.summary(s)=="目前沒有訂單"
        print("All v2.1 LTS tests passed.")
        print(summary)
        print(st)
if __name__=="__main__":run()
