"""สร้าง URL ค้นหา Divine Orb แล้วเปิด browser — ตาดูว่าหน้า trade fill+search ให้ไหม"""
import json, urllib.parse, webbrowser

LEAGUE = "Return of the Ancients"   # <-- แก้ให้ตรง
GAME = "poe2"  # "poe1" หรือ "poe2"

base = ("https://www.pathofexile.com/trade2/search/" if GAME == "poe2"
        else "https://www.pathofexile.com/trade/search/") + urllib.parse.quote(LEAGUE)
q = {"query": {"status": {"option": "online"}, "type": "Divine Orb"},
     "sort": {"price": "asc"}}
url = base + "?q=" + urllib.parse.quote(json.dumps(q, separators=(",", ":")))
print(url)
webbrowser.open(url)
