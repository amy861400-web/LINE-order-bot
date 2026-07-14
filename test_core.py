import tempfile
from pathlib import Path
from database import OrderDatabase
from order_manager import OrderManager
from parser import OrderParser
def run():
    with tempfile.TemporaryDirectory() as t:
        path=str(Path(t)/'orders.db');m=OrderManager(OrderDatabase(path));p=OrderParser();s='group:test';m.start_new_round(s)
        for msg in ['炒麵大x3=150','綜合湯X3=180','雞腿飯×2=210','滷蛋 * 4 = 60','炒麵小+隔間肉湯=100謝謝','炒麵 大 +荷包蛋']:
            r=p.parse(msg);assert r['action']=='add',r;assert m.apply(s,'u1','Wu Yi Ru',r)
        m2=OrderManager(OrderDatabase(path));assert m2.is_active(s);summary=m2.summary(s)
        for line in ['炒麵 大 4','炒麵 小 1','綜合湯 3','雞腿飯 2','滷蛋 4','隔間肉湯 1','荷包蛋 1','本輪共 1 人','共 16 份']:assert line in summary,(line,summary)
        print('All v2.0 LTS tests passed.')
if __name__=='__main__':run()
