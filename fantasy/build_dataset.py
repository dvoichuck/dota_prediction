"""Build a merged fantasy dataset: site stats (by steamId) + player name/team (OpenDota)."""
import json
import csv
import io
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)

CDP_FILE = r"C:\Users\Dima\.cursor\browser-logs\cdp-response-Runtime.evaluate-2026-08-07T06-23-20-322Z.json"
PROPLAYERS = os.path.join(ROOT, "proplayers.json")

STEAM64_BASE = 76561197960265728


def load_site_stats():
    with open(CDP_FILE, "r", encoding="utf-8") as f:
        cdp = json.load(f)
    csv_text = cdp["result"]["value"]["csv"]
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = []
    for r in reader:
        rec = {}
        for k, v in r.items():
            if k == "steamId":
                rec[k] = int(v)
            else:
                rec[k] = float(v) if v not in ("", None) else 0.0
        rows.append(rec)
    return rows


def load_proplayers():
    with open(PROPLAYERS, "r", encoding="utf-8") as f:
        pros = json.load(f)
    by_acc = {}
    for p in pros:
        acc = p.get("account_id")
        if acc is None:
            continue
        by_acc[int(acc)] = {
            "name": p.get("name"),
            "team_name": p.get("team_name"),
            "team_tag": p.get("team_tag"),
            "personaname": p.get("personaname"),
        }
    return by_acc


def main():
    rows = load_site_stats()
    pros = load_proplayers()
    merged = []
    unmatched = []
    for r in rows:
        acc = r["steamId"] - STEAM64_BASE
        info = pros.get(acc)
        rec = dict(r)
        rec["account_id"] = acc
        if info:
            rec["name"] = info["name"] or info["personaname"]
            rec["team_name"] = info["team_name"]
            rec["team_tag"] = info["team_tag"]
        else:
            rec["name"] = None
            rec["team_name"] = None
            rec["team_tag"] = None
            unmatched.append(acc)
        merged.append(rec)

    matched = sum(1 for m in merged if m["name"])
    print(f"players: {len(merged)}  matched: {matched}  unmatched: {len(unmatched)}")

    # Normalize OpenDota team_name -> our TI15 consensus team names.
    TEAM_MAP = {
        "1w": "Iron Wing (1win)",
        "Aurora Gaming": "Aurora Gaming",
        "BoomBoys": "BoomBoys",
        "GamerLegion": "GamerLegion",
        "HULIGANI": "HULIGANI",
        "L1GA TEAM": "HULIGANI",  # 2 HULIGANI players carry a stale OpenDota tag
        "LGD Gaming": "LGD Gaming",
        "Nigma Galaxy": "Nigma Galaxy",
        "OG": "OG",
        "TEAM VISION": "Team Vision",
        "Team Falcons": "Team Falcons",
        "Team Liquid": "Team Liquid",
        "Team Resilience": "Team Resilience",
        "Team Spirit": "Team Spirit",
        "Team Yandex": "Team Yandex",
        "Vici Gaming": "Vici Gaming",
        "Xtreme Gaming": "Xtreme Gaming",
    }
    for m in merged:
        raw = (m["team_name"] or "").strip()
        m["team"] = TEAM_MAP.get(raw, raw)

    # Assign fantasy roles per team from stat profile:
    #  - 2 highest wardsAverage  -> support
    #  - highest runesAverage of the rest -> mid (runes is a clean mid signal)
    #  - remaining -> core
    teams = {}
    for m in merged:
        teams.setdefault(m["team"], []).append(m)
    for team, ps in teams.items():
        by_wards = sorted(ps, key=lambda x: -x["wardsAverage"])
        supports = by_wards[:2]
        rest = by_wards[2:]
        for p in supports:
            p["role"] = "support"
        if rest:
            mid = max(rest, key=lambda x: x["runesAverage"])
            mid["role"] = "mid"
            for p in rest:
                if p is not mid:
                    p["role"] = "core"

    with open(os.path.join(BASE, "players.json"), "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    ROLE_ORDER = {"core": 0, "mid": 1, "support": 2}
    print("\n=== ROSTERS by role (Core x2 / Mid x1 / Support x2) ===")
    for team in sorted(teams):
        ps = sorted(teams[team], key=lambda x: (ROLE_ORDER.get(x.get("role"), 9), -x["gpmAverage"]))
        print(f"\n[{team}]  ({len(ps)} players)")
        for m in ps:
            print(f"  {m.get('role','?'):<8} {m['name']:<16} gpm={m['gpmAverage']:>4.0f} "
                  f"runes={m['runesAverage']:>4.0f} wards={m['wardsAverage']:>4.0f} games={m['gamesPlayed']:.0f}")
    if unmatched:
        print("\n=== UNMATCHED account_ids ===")
        print(unmatched)


if __name__ == "__main__":
    main()
