import json, urllib.parse, webbrowser, pathlib, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

LEAGUE = "Runes of Aldur"
GAME = "poe2"  # "poe1" or "poe2"

base = ("https://www.pathofexile.com/trade2/search/" if GAME == "poe2"
        else "https://www.pathofexile.com/trade/search/") + urllib.parse.quote(LEAGUE)
q = {"query": {"status": {"option": "online"}, "type": "Divine Orb"},
     "sort": {"price": "asc"}}
url = base + "?q=" + urllib.parse.quote(json.dumps(q, separators=(",", ":")))

out = pathlib.Path(__file__).parent / "probe_trade_url_result.txt"
out.write_text(url, encoding="utf-8")
print(url)
print(f"\n>>> URL saved: {out}")
print(">>> Opening browser -- check if trade page loads Divine Orb + auto-searches")
webbrowser.open(url)
input("Press Enter to close...")
