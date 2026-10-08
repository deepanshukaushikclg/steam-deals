import json, os

free = json.load(open("data.json"))["free"]
try:
    seen = set(json.load(open("seen.json")))
except Exception:
    seen = set()

new = [g for g in free if g["url"] not in seen]
if not new:
    print("no new free games")
    raise SystemExit(0)

owner = os.environ.get("GITHUB_REPOSITORY_OWNER", "")
title = f"{len(new)} Steam game(s) free now: " + ", ".join(g["title"] for g in new[:3])
lines = [f'- [{g["title"]}]({g["url"]}) (worth Rs {g["price_inr"]:,})' for g in new]
body = ("@" + owner + "\n\n" if owner else "") + "\n".join(lines)

open("issue.md", "w").write(title + "\n" + body)
json.dump(sorted(seen | {g["url"] for g in free}), open("seen.json", "w"))
print("issue.md written for", len(new))
