from __future__ import annotations
from collections import Counter,OrderedDict
from database import OrderDatabase
from parser import normalize_food_name
class OrderManager:
    def __init__(self,db=None):self.db=db or OrderDatabase()
    def start_new_round(self,scope_id):self.db.start_round(scope_id)
    def is_active(self,scope_id):return self.db.active_round(scope_id) is not None
    def close(self,scope_id):self.db.close_round(scope_id)
    def clear(self,scope_id):self.db.clear_orders(scope_id)
    def apply(self,scope_id,user_id,user_name,result):
        if not self.is_active(scope_id) or not isinstance(result,dict):return False
        a=str(result.get('action','ignore')).lower().strip()
        if a=='ignore':return False
        if a=='cancel':self.db.cancel_user(scope_id,user_id);return True
        if a=='copy':
            target=str(result.get('target','last') or 'last').strip();sid=self.db.last_order_user_id(scope_id) if target=='last' else self.db.find_user_id_by_name(scope_id,target)
            if not sid:return False
            rows=self.db.user_items(scope_id,sid)
            if not rows:return False
            return self.db.set_items(scope_id,user_id,user_name,{normalize_food_name(str(r['food_name'])):int(r['qty']) for r in rows})
        items=Counter()
        for item in result.get('items',[]):
            if not isinstance(item,dict):continue
            name=normalize_food_name(item.get('name',''))
            if not name:continue
            try:q=int(item.get('qty',1) or 1)
            except:q=1
            if 1<=q<=50:items[name]+=q
        if not items:return False
        return self.db.set_items(scope_id,user_id,user_name,dict(items)) if a=='set' else self.db.add_items(scope_id,user_id,user_name,dict(items)) if a=='add' else False
    def my_order(self,scope_id,user_id):
        rows=self.db.user_items(scope_id,user_id)
        return '目前沒有訂單' if not rows else '\n'.join(f"{r['food_name']} {r['qty']}" for r in sorted(rows,key=lambda r:str(r['food_name']).casefold()))
    def summary(self,scope_id):
        rows=self.db.all_orders(scope_id)
        if not rows:return '目前沒有訂單'
        users=OrderedDict();total=Counter();uids=set()
        for r in rows:
            name=str(r['user_name']);food=str(r['food_name']);q=int(r['qty']);uids.add(str(r['user_id']));users.setdefault(name,Counter());users[name][food]+=q;total[food]+=q
        lines=[]
        for name,items in users.items():
            lines.append(f'{name} :');lines += [f'{f} {q}' for f,q in sorted(items.items(),key=lambda x:x[0].casefold())];lines.append('')
        lines+=['----------------',''];lines += [f'{f} {q}' for f,q in sorted(total.items(),key=lambda x:x[0].casefold())];lines += ['',f'本輪共 {len(uids)} 人',f'共 {sum(total.values())} 份'];return '\n'.join(lines).strip()
