import json, re, time, urllib.request, urllib.parse, datetime

LIMIT_INR = 250

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "freegames-site/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

# USD -> INR
try:
    rate = float(get("https://open.er-api.com/v6/latest/USD")["rates"]["INR"])
except Exception:
    rate = 88.0

# Free right now (Steam giveaways, "worth" = original price in USD)
free = []
try:
    for g in get("https://www.gamerpower.com/api/giveaways?platform=steam&type=game"):
        if g.get("status") != "Active":
            continue
        m = re.search(r"[\d.]+", g.get("worth") or "")
        worth = float(m.group()) if m else 0.0
        free.append({"title": re.sub(r"\s*\(Steam\)( Giveaway)?$", "", g["title"]),
                     "price_inr": round(worth * rate),
                     "image": g.get("image") or g.get("thumbnail"),
                     "url": g["open_giveaway_url"]})
except Exception as e:
    print("gamerpower failed:", e)

# Paid games on sale at or below LIMIT_INR (Steam store = CheapShark storeID 1)
cheap, seen_ids = [], set()
try:
    for page in range(60):
        q = urllib.parse.urlencode({"storeID": 1, "onSale": 1, "pageSize": 60, "pageNumber": page,
                                    "upperPrice": round(LIMIT_IN*6  / rate, 2), "sortBy": "Price"})
        rows = get("https://www.cheapshark.com/api/1.0/deals?" + q)
        for d in rows:
            sale, normal = float(d["salePrice"]), float(d["normalPrice"])
            app = d.get("steamAppID")
            if sale <= 0 or not app or app in seen_ids:
                continue
            seen_ids.add(app)
            cheap.append({"title": d["title"],
                          "price_inr": round(normal * rate),
                          "sale_inr": round(sale * rate),
                          "off": round((1 - sale / normal) * 100) if normal else 0,
                          "image": "https://cdn.akamai.steamstatic.com/steam/apps/%s/header.jpg" % app,
                          "url": "https://store.steampowered.com/app/" + app})
        if len(rows) < 60:
            break
        time.sleep(0.3)
except Exception as e:
    print("cheapshark failed:", e)

free.sort(key=lambda x: -x["price_inr"])
cheap.sort(key=lambda x: -x["price_inr"])

json.dump({"updated": datetime.datetime.utcnow().isoformat() + "Z",
           "limit_inr": LIMIT_INR, "free": free, "cheap": cheap},
          open("data.json", "w"), indent=1)
print(len(free), "free,", len(cheap), "cheap")
