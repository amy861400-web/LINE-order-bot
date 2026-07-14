from __future__ import annotations
import re
from collections import Counter
TOTAL_RE=re.compile(r"^\s*(共|總共|合計|小計)\s*[$＄]?\s*\d+\s*(元)?\s*(謝謝|感謝)?\s*$",re.I)
URL_RE=re.compile(r"https?://\S+",re.I); MENTION_RE=re.compile(r"@\S+")
NOISE={"謝謝","謝謝唷","謝謝你","感謝","感恩","麻煩","拜託","ok","收到","好","好的","午安","早安","晚安","哈哈","哈哈哈","已付款","付款了","不用","不用了","測試","測試版","test","testing","目前","沒問題","統計","結單","清空","結束"}
HINTS=("飯","麵","粥","湯","鍋","排","雞","鴨","鵝","魚","蝦","肉","蛋","餃","包","堡","吐司","三明治","沙拉","飲","茶","咖啡","奶","豆漿","薯","捲","羹","燴","便當","披薩","炒","滷","煎","炸","烤")
NOTES=["飯半","半飯","少飯","飯少","多飯","飯多","加蛋","荷包蛋","滷蛋","不要菜","不加菜","少菜","多菜","不要辣","不辣","微辣","小辣","中辣","大辣","不要蔥","不加蔥","不要香菜","不加香菜","不要醬","醬少","醬多"]
def normalize_food_name(name):
    t=str(name or '').replace('　',' ').strip(); t=re.sub(r'\s+',' ',t); t=re.sub(r'\s*([大中小])$',r' \1',t)
    for n in sorted(NOTES,key=len,reverse=True): t=re.sub(rf'\s*{re.escape(n)}$',f' {n}',t)
    return re.sub(r'\s+',' ',t).strip()
class OrderParser:
    def parse(self,message):
        t=MENTION_RE.sub(' ',message or '').strip()
        if self._ignore(t):return {'action':'ignore'}
        c=re.sub(r'\s+','',t)
        if c in {'取消','取消我的','取消我的訂單','不要了','不用了','取消訂單'}:return {'action':'cancel'}
        if '一樣' in c:
            target=c
            for token in ('我要','我也要','跟','和','一樣','同樣'):target=target.replace(token,'')
            target=target.strip() or 'last'
            if target in {'上一個','上一位','前一個','前一位'}:target='last'
            return {'action':'copy','target':target}
        action='add'; w=t
        if re.match(r'^\s*(改成|換成)',w):w=re.sub(r'^\s*(改成|換成)','',w,count=1).strip();action='set'
        elif re.match(r'^\s*(改|換)',w):w=re.sub(r'^\s*(改|換)','',w,count=1).strip();action='set'
        elif re.match(r'^\s*(再加|加|\+)',w):w=re.sub(r'^\s*(再加|加|\+)','',w,count=1).strip()
        items=self._extract(w); return {'action':action,'items':items} if items else {'action':'ignore'}
    def _extract(self,text):
        parts=re.split(r'(?:[\n,，、；;]+|\s*[+＋&＆]\s*|\s+(?:和|跟)\s+)',text); out=Counter()
        for raw in parts:
            line=raw.strip()
            if not line or self._ignore(line) or TOTAL_RE.fullmatch(line):continue
            qty=1; m=re.search(r'(?:[*xX×]\s*(\d+)|(\d+)\s*份)',line)
            if m:qty=int(m.group(1) or m.group(2))
            line=re.sub(r'[$＄]?\s*\d*\s*[*xX×]\s*\d+\s*=\s*\d+',' ',line); line=re.sub(r'[$＄]?\s*\d+\s*(元)?',' ',line); line=re.sub(r'[*xX×]\s*\d+',' ',line)
            for word in ('我要','我想要','來一個','來一份','麻煩','請問','謝謝','感謝','感恩','拜託','ok','OK'):line=line.replace(word,' ')
            name=self._clean(line)
            if name and self._food(name):out[normalize_food_name(name)]+=max(1,min(qty,50))
        return [{'name':n,'qty':q} for n,q in out.items()]
    def _ignore(self,t):
        v=(t or '').strip(); return (not v or v.lower() in NOISE or TOTAL_RE.fullmatch(v) or URL_RE.fullmatch(v) or not re.search(r'[\u4e00-\u9fffA-Za-z0-9]',v))
    def _food(self,t):
        if t.lower() in NOISE or len(t)<2 or URL_RE.search(t):return False
        if any(h in t for h in HINTS):return True
        return bool(re.fullmatch(r'[\u4e00-\u9fffA-Za-z]{2,12}',t)) and not any(x in t for x in ('開會','今天','明天','下午','上午','請假','測試','付款','收到','公告','結單'))
    def _clean(self,t):
        v=URL_RE.sub(' ',t or '');v=MENTION_RE.sub(' ',v);v=re.sub(r'(共|總共|合計|小計)\s*\d+\s*(元)?',' ',v);v=re.sub(r'\s+',' ',v);return v.strip(' ：:-＝=,，。.!！?？()（）[]【】')
