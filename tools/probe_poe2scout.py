"""tools/probe_poe2scout.py — สำรวจ API ของ poe2scout.com"""
import json, re, urllib.request, urllib.error

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

def get(url, accept="application/json"):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status, r.read(), r.headers.get("Content-Type", "")

BASE = "https://poe2scout.com"

# 1) หา docs/spec
print("=== docs/spec ===")
for p in ["/docs", "/swagger", "/openapi.json", "/api/docs", "/redoc", "/graphql"]:
    try:
        s, raw, ct = get(BASE + p)
        print(f"200 {p} | {ct[:50]} | {raw[:120]}")
    except urllib.error.HTTPError as e:
        print(f"{e.code} {p}")
    except Exception as e:
        print(f"ERR {p} — {e}")

# 2) scan HTML หน้าหลักหา API path
print("\n=== HTML scan ===")
try:
    _, raw, _ = get(BASE, "text/html")
    html = raw.decode("utf-8", errors="replace")
    apis  = list(set(re.findall(r'''[\"'](/api/[^\"'<> ]{2,80})[\"'|]''', html)))
    fetch = list(set(re.findall(r'''fetch\([\"'](https?://[^\"']{5,100})[\"']''', html)))
    print("API refs:", apis[:30])
    print("fetch():", fetch[:10])
    # หา src ของ JS bundles
    scripts = re.findall(r'src=["\']([^"\']+\.js[^"\']*)["\']', html)
    print("JS bundles:", scripts[:10])
except Exception as e:
    print("ERR:", e)

# 3) ลอง scan JS bundle ตัวแรก
print("\n=== JS bundle scan ===")
try:
    _, raw, _ = get(BASE, "text/html")
    html = raw.decode("utf-8", errors="replace")
    scripts = re.findall(r'src=["\']([^"\']+\.js[^"\']*)["\']', html)
    for src in scripts[:5]:
        js_url = src if src.startswith("http") else BASE + src
        try:
            _, js_raw, _ = get(js_url, "*/*")
            js = js_raw.decode("utf-8", errors="replace")
            found = list(set(re.findall(r'''[\"'](/api/[^\"'<> ]{2,80})[\"'|]''', js)))
            if found:
                print(f"In {src}:")
                for f in found[:20]:
                    print(f"  {f}")
        except Exception as e:
            print(f"ERR {src}: {e}")
except Exception as e:
    print("ERR:", e)
