import json
import re
import time
import urllib.request
import urllib.parse
import datetime

LIMIT_INR = 250

GAMERPOWER_URL = "https://www.gamerpower.com/api/giveaways?platform=steam&type=game"
CHEAPSHARK_URL = "https://www.cheapshark.com/api/1.0/deals"


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


# ============================================================
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

        title = g.get("title", "").strip()

        # Remove Steam suffix
        title = re.sub(
            r"\s*\(Steam\)(\s*Giveaway)?$",
            "",
            title,
            flags=re.IGNORECASE
        ).strip()

        # "worth" is usually something like "$19.99"
        worth_text = g.get("worth") or ""

        match = re.search(r"[\d.]+", worth_text)

        if match:
            try:
                worth_usd = float(match.group())
            except ValueError:
                worth_usd = 0.0
        else:
            worth_usd = 0.0

        worth_inr = round(worth_usd * rate)

        free.append({
            "title": title,
            "price_inr": worth_inr,
            "image": g.get("image") or g.get("thumbnail"),
            "url": g.get("open_giveaway_url")
        })

except Exception as e:
    print("GamerPower failed:", e)


# ============================================================
# STEAM SALES
# ============================================================

cheap = []
seen_apps = set()

# Convert ₹250 to USD.
# Add a tiny buffer because of currency/API rounding.
max_price_usd = LIMIT_INR / rate + 0.10

try:

    page = 0

    while True:

        params = {
            "storeID": 1,              # Steam
            "onSale": 1,               # Only games currently on sale
            "pageSize": 100,           # More results per request
            "pageNumber": page,
            "upperPrice": round(max_price_usd, 2),
            "sortBy": "Price"
        }

        url = CHEAPSHARK_URL + "?" + urllib.parse.urlencode(params)

        print("Fetching Steam deals page:", page)

        rows = get(url)

        if not rows:
            break

        for d in rows:

            try:
                sale_usd = float(d.get("salePrice", 0))
                normal_usd = float(d.get("normalPrice", 0))
            except (TypeError, ValueError):
                continue

            app_id = d.get("steamAppID")

            # We need a Steam App ID to link to the game.
            if not app_id:
                continue

            # Avoid duplicates
            if app_id in seen_apps:
                continue

            # Ignore invalid prices
            if sale_usd <= 0:
                continue

            # IMPORTANT:
            # Check the actual INR sale price ourselves.
            sale_inr = sale_usd * rate

            if sale_inr > LIMIT_INR:
                continue

            seen_apps.add(app_id)

            normal_inr = normal_usd * rate

            if normal_usd > 0:
                discount = round(
                    (1 - sale_usd / normal_usd) * 100
                )
            else:
                discount = 0

            cheap.append({
                "title": d.get("title", "").strip(),

                # Original price
                "price_inr": round(normal_inr),

                # Current sale price
                "sale_inr": round(sale_inr),

                # USD values are useful if you want them later
                "price_usd": round(normal_usd, 2),
                "sale_usd": round(sale_usd, 2),

                "off": discount,

                "image": (
                    "https://cdn.akamai.steamstatic.com/"
                    f"steam/apps/{app_id}/header.jpg"
                ),

                "url": (
                    "https://store.steampowered.com/app/"
                    + str(app_id)
                ),

                "steam_app_id": str(app_id)
            })

        # If fewer than pageSize results are returned,
        # we've reached the final page.
        if len(rows) < 100:
            break

        page += 1

        # Prevent hammering the API
        time.sleep(0.3)

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
