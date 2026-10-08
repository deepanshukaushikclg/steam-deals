import html as htmllib, json, math, re, time, urllib.error, urllib.request, urllib.parse, datetime

GAMERPOWER_URL = "https://www.gamerpower.com/api/giveaways?platform=steam&type=game"
LIMIT_INR = 250      # "Under" section ceiling
# CheapShark serves ~50 pages (3000 deals) per query, so fetch in price bands (INR)
# Candidates are found by USD price (converted) but final INR prices come from Steam India,
# which is often far cheaper than the USD conversion, so search well above LIMIT_INR.
BANDS_INR = [0, 20, 30, 40, 50, 60, 70, 80, 100, 125, 150, 200, 250, 300, 400, 500, 650, 800, 1000, 1250]
MAX_PAGES = 55
PAUSE = 0.6

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "freegames-site/1.0",
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

def iso_unix(ts):
    try:
        ts = int(ts)
        return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if ts > 0 else None
    except Exception:
        return None

def iso_gp(s):  # GamerPower: "2026-10-01 12:00:00" or "N/A"
    try:
        return datetime.datetime.strptime(s.strip(), "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None

def posint(x):  # CheapShark uses "0" for "unknown" -> None (never invent values)
    try:
        v = int(float(x))
        return v if v > 0 else None
    except Exception:
        return None

def est_rarity(review_count):
    """Estimated Rarity (0-100): fewer Steam reviews = rarer/more obscure.
    100 * (1 - log10(1 + reviews) / 5), clamped; 100k+ reviews -> 0.
    A proxy built from public review counts, NOT an official rarity metric."""
    if not review_count:
        return None
    return round(100 * max(0.0, 1 - math.log10(1 + review_count) / 5), 1)

# USD -> INR
try:
    rate = float(get("https://open.er-api.com/v6/latest/USD")["rates"]["INR"])
except Exception as e:
    print("Exchange rate failed:", e)
    rate = 88.0
print("USD -> INR:", rate)

# Free right now (Steam giveaways, "worth" = original price in USD)
free = []
try:
    for g in get(GAMERPOWER_URL):
        if g.get("status") != "Active":
            continue
        m = re.search(r"[\d.]+", g.get("worth") or "")
        worth = round((float(m.group()) if m else 0.0) * rate)
        free.append({"id": "gp-%s" % g.get("id"),
                     "title": re.sub(r"\s*\(Steam\)( Giveaway)?$", "", g["title"]),
                     "price_inr": worth, "sale_inr": 0, "off": 100, "savings_inr": worth,
                     "image": g.get("image") or g.get("thumbnail"),
                     "url": g["open_giveaway_url"],
                     "deal_start": iso_gp(g.get("published_date") or ""),
                     "expiry_date": iso_gp(g.get("end_date") or ""),
                     "claims": posint(g.get("users"))})   # giveaway claim count = popularity
except Exception as e:
    print("gamerpower failed:", e)

# Paid games on sale at or below LIMIT_INR (Steam store = CheapShark storeID 1)
cheap, ids = [], set()
for lo, hi in zip(BANDS_INR, BANDS_INR[1:]):
    n_band = 0
    for page in range(MAX_PAGES):
        q = urllib.parse.urlencode({"storeID": 1, "onSale": 1, "pageSize": 60, "pageNumber": page,
                                    "lowerPrice": round(lo / rate, 2), "upperPrice": round(hi / rate, 2),
                                    "sortBy": "Price"})
        try:
            deals = get("https://www.cheapshark.com/api/1.0/deals?" + q)
        except urllib.error.HTTPError as e:
            if e.code == 400 and page > 0:   # CheapShark page limit reached
                if page >= 50:
                    print("  band ₹%d-%d hit CheapShark's page limit; split it into smaller bands" % (lo, hi))
                break
            print("CheapShark failed:", e); break
        except Exception as e:
            print("CheapShark failed:", e); break
        if not deals:
            break
        for d in deals:
            sale, normal = float(d["salePrice"]), float(d["normalPrice"])
            if sale <= 0 or not d.get("steamAppID") or d["dealID"] in ids:
                continue
            ids.add(d["dealID"]); n_band += 1
            reviews = posint(d.get("steamRatingCount"))
            try:
                score = float(d.get("dealRating")) or None
            except Exception:
                score = None
            cheap.append({"id": "cs-%s" % d["steamAppID"], "title": d["title"],
                          "price_inr": round(normal * rate), "sale_inr": round(sale * rate),
                          "off": round((1 - sale / normal) * 100) if normal else 0,
                          "savings_inr": round((normal - sale) * rate),
                          "image": "https://cdn.akamai.steamstatic.com/steam/apps/%s/header.jpg" % d["steamAppID"],
                          "url": "https://store.steampowered.com/app/" + d["steamAppID"],
                          "release_date": iso_unix(d.get("releaseDate")),
                          "deal_start": iso_unix(d.get("lastChange")),   # when price last changed
                          "rating_pct": posint(d.get("steamRatingPercent")),
                          "rating_text": d.get("steamRatingText") or None,
                          "review_count": reviews,
                          "metacritic": posint(d.get("metacriticScore")),
                          "deal_score": score,
                          "est_rarity": est_rarity(reviews)})
        if len(deals) < 60:
            break
        time.sleep(PAUSE)
    print("band ₹%d-%d: %d deals" % (lo, hi, n_band), flush=True)

# Real Steam India (INR) prices for the candidates
def steam_inr(appids):
    out, answered = {}, set()
    for i in range(0, len(appids), 100):
        chunk = appids[i:i + 100]
        try:
            data = get("https://store.steampowered.com/api/appdetails?" + urllib.parse.urlencode(
                {"appids": ",".join(chunk), "cc": "in", "filters": "price_overview"}))
            for aid, v in data.items():
                answered.add(aid)
                d = v.get("data") if v.get("success") else None
                po = d.get("price_overview") if isinstance(d, dict) else None
                if po and po.get("currency") == "INR":
                    out[aid] = po
        except Exception as e:
            print("steam price batch failed:", e)
        print("  steam prices %d/%d" % (min(i + 100, len(appids)), len(appids)), flush=True)
        time.sleep(1.5)
    return out, answered

# Steam's own India store search (specials only, cheapest first) as the main candidate source
def steam_search(max_pages=120, count=50):
    found, start = {}, 0
    for _ in range(max_pages):
        try:
            d = get("https://store.steampowered.com/search/results/?" + urllib.parse.urlencode(
                {"query": "", "start": start, "count": count, "specials": 1, "cc": "in", "l": "english",
                 "sort_by": "Price_ASC", "category1": 998, "infinite": 1}))
        except Exception as e:
            print("steam search failed:", e); break
        page = d.get("results_html") or ""
        rows = [r for r in re.split(r'(?=<a [^>]*data-ds-appid=)', page) if "data-ds-appid" in r]
        if not rows:
            break
        prices = []
        for r in rows:
            m = re.search(r'data-ds-appid="(\d+)', r)
            if not m:
                continue
            t = re.search(r'<span class="title">(.*?)</span>', r, re.S)
            p = re.search(r'data-price-final="(\d+)"', r)
            if p and int(p.group(1)) > 0:
                prices.append(int(p.group(1)) / 100)
            found.setdefault(m.group(1), htmllib.unescape(t.group(1)).strip() if t else None)
        print("  steam search %d results, %d candidates" % (start + len(rows), len(found)), flush=True)
        if prices and min(prices) > LIMIT_INR:   # sorted by price: nothing cheaper follows
            break
        start += count
        if start >= (d.get("total_count") or 0):
            break
        time.sleep(1.5)
    return found

by_app = {c["id"][3:] for c in cheap}
steam_only = set()
for aid, title in steam_search().items():
    if aid in by_app or not title:
        continue
    steam_only.add(aid)
    cheap.append({"id": "cs-" + aid, "title": title,
                  "price_inr": 0, "sale_inr": 0, "off": 0, "savings_inr": 0,
                  "image": "https://cdn.akamai.steamstatic.com/steam/apps/%s/header.jpg" % aid,
                  "url": "https://store.steampowered.com/app/" + aid})
print("candidates:", len(cheap), "(%d from Steam search only)" % len(steam_only))

prices, answered = steam_inr([c["id"][3:] for c in cheap])
final = []
for c in cheap:
    aid = c["id"][3:]
    po = prices.get(aid)
    if po:
        init, fin = po["initial"] / 100, po["final"] / 100
        if po.get("discount_percent", 0) <= 0 or fin <= 0 or fin > LIMIT_INR:
            continue
        c.update(price_inr=round(init), sale_inr=round(fin), off=po["discount_percent"],
                 savings_inr=round(init - fin), price_source="steam_in")
    elif aid in steam_only or aid in answered or c["sale_inr"] > LIMIT_INR:
        continue      # Steam India has no price for it, or converted price too high
    else:
        c["price_source"] = "converted"   # Steam request failed: keep USD conversion
    final.append(c)
cheap = final

free.sort(key=lambda x: x["price_inr"], reverse=True)   # highest original value first
cheap.sort(key=lambda x: x["sale_inr"])                  # cheapest sale price first

output = {"updated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
          "currency": {"from": "USD", "to": "INR", "rate": rate},
          "limit_inr": LIMIT_INR, "free": free, "cheap": cheap}

with open("data.json", "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print("\nDONE\nFree games:", len(free), "\nSteam games under ₹%d:" % LIMIT_INR, len(cheap))
