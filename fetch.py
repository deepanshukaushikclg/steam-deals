import json, math, re, time, urllib.request, urllib.parse, datetime

LIMIT_INR = 250      # "Under" section ceiling
PAGES = 3            # CheapShark pages of 60 deals (polite: 1s pause between)

def get(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "freegames-site/1.0",
            "Accept": "application/json"
        }
    )

    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

def iso_unix(ts):
    try:
        ts = int(ts)
        return datetime.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%dT%H:%M:%SZ") if ts > 0 else None
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
# ============================================================

try:
    currency_data = get("https://open.er-api.com/v6/latest/USD")
    rate = float(currency_data["rates"]["INR"])
except Exception as e:
    print("Exchange rate failed:", e)
    rate = 88.0

print("USD -> INR:", rate)


# ============================================================
# FREE GAMES
# ============================================================

free = []

try:
    giveaways = get(GAMERPOWER_URL)

    for g in giveaways:

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
try:
    for page in range(PAGES):
        q = urllib.parse.urlencode({"storeID": 1, "onSale": 1, "pageSize": 60, "pageNumber": page,
                                    "upperPrice": round(LIMIT_INR / rate, 2), "sortBy": "Price"})
        deals = get("https://www.cheapshark.com/api/1.0/deals?" + q)
        if not deals:
            break
        for d in deals:
            sale, normal = float(d["salePrice"]), float(d["normalPrice"])
            if sale <= 0 or not d.get("steamAppID") or d["dealID"] in ids:
                continue
            ids.add(d["dealID"])
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
        time.sleep(1)
except Exception as e:
    print("CheapShark failed:", e)


# ============================================================
# SORTING
# ============================================================

# Free games:
# Highest original value first
free.sort(
    key=lambda x: x["price_inr"],
    reverse=True
)

# Paid games:
# Cheapest sale price first
cheap.sort(
    key=lambda x: x["sale_inr"]
)


# ============================================================
# OUTPUT
# ============================================================

output = {
    "updated": datetime.datetime.now(
        datetime.timezone.utc
    ).isoformat(),

    "currency": {
        "from": "USD",
        "to": "INR",
        "rate": rate
    },

    "limit_inr": LIMIT_INR,

    "free": free,

    "cheap": cheap
}


with open(
    "data.json",
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        output,
        f,
        indent=2,
        ensure_ascii=False
    )


print()
print("=" * 50)
print("DONE")
print("=" * 50)
print("Free games:", len(free))
print("Steam games under ₹250:", len(cheap))
print("Exchange rate:", rate)
print("Limit: ₹", LIMIT_INR)
