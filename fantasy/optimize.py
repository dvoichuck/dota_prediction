"""
Fantasy pick layer for TI15 -- rules-accurate version.
=================================================================
Scoring follows the in-game fantasy glossary:

* A battle standard holds 3 EMBLEMS. You choose which characteristics
  to equip, so a player's value = the sum of their BEST 3 of the 18
  characteristics (not a flat average -- that is only the site's sort key).
* The 18 characteristics come in 3 colors:
    RED   : kills, deaths, creeps, gpm, madstone, towers
    BLUE  : wards, camps, runes, watchers, smokes, lotuses
    GREEN : roshan, teamfight, stuns, tormentor, fb, courier
* precomputed_stats values are ALREADY per-game fantasy points
  (e.g. deaths = 1950 - 195*deaths, so deathsTop=1950 means a 0-death game).
* Core/Support are pairs sharing one standard -> we average the pair per
  characteristic first, then take the best 3. Mid is a single player.
* Emblem quality (+10%..+150%) and traits multiply on top roughly
  uniformly, so they do not change the ranking; we report the base score.

Layer output per role-unit:
    EV = best-3 emblem score  x  team game-exposure weight (from the sim)
plus the RECOMMENDED 3 emblems to equip on that unit.

Run:  python fantasy/optimize.py                 (default: phase=main)
      python fantasy/optimize.py --phase group
      python fantasy/optimize.py --metric top     (ceiling instead of average)
      python fantasy/optimize.py --emblems 3      (emblem slots per standard)
      python fantasy/optimize.py --sims 200000
"""
import argparse
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ti15_swiss_sim import compute_probs, TEAMS as SIM_TEAMS  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))

# (key, color, short label) for all 18 fantasy characteristics
CHARS = [
    ("kills", "R", "Вбивства"), ("deaths", "R", "Смерті"),
    ("creeps", "R", "Кріпи"), ("gpm", "R", "ЗЗХ"),
    ("madstone", "R", "Лютит"), ("towers", "R", "Вежі"),
    ("wards", "B", "Варди"), ("camps", "B", "Табори"),
    ("runes", "B", "Руни"), ("watchers", "B", "Споглядачі"),
    ("smokes", "B", "Дими"), ("lotuses", "B", "Лотоси"),
    ("roshan", "G", "Рошан"), ("teamfight", "G", "Тімфайти"),
    ("stuns", "G", "Стани"), ("tormentor", "G", "Мучителі"),
    ("fb", "G", "Перша кров"), ("courier", "G", "Кур'єри"),
]

SIM_TO_DATA = {t: t for t in SIM_TEAMS}
SIM_TO_DATA["1win Team"] = "Iron Wing (1win)"


def load_players():
    with open(os.path.join(BASE, "players.json"), "r", encoding="utf-8") as f:
        return json.load(f)


def unit_char_values(players, metric):
    """Pair-averaged value per characteristic for a role-unit."""
    suffix = "Average" if metric == "avg" else "Top"
    vals = {}
    for key, _c, _l in CHARS:
        vals[key] = sum(p.get(key + suffix, 0.0) for p in players) / len(players)
    return vals


def best_emblems(char_vals, n):
    """Return (score, chosen) where chosen = top-n characteristics."""
    ranked = sorted(CHARS, key=lambda c: -char_vals[c[0]])
    chosen = ranked[:n]
    score = sum(char_vals[c[0]] for c in chosen)
    return score, chosen


def build_units(players, metric, n_emblems):
    teams = {}
    for p in players:
        teams.setdefault(p["team"], {"core": [], "mid": [], "support": []})
        teams[p["team"]][p.get("role", "core")].append(p)

    units = {"core": [], "mid": [], "support": []}
    for team, roles in teams.items():
        for role in ("core", "mid", "support"):
            ps = roles[role]
            if not ps:
                continue
            cvals = unit_char_values(ps, metric)
            score, chosen = best_emblems(cvals, n_emblems)
            units[role].append({
                "team": team,
                "players": [p["name"] for p in ps],
                "score": score,
                "emblems": [{"key": k, "color": c, "label": l,
                             "value": round(cvals[k])} for k, c, l in chosen],
                "min_games": min(p["gamesPlayed"] for p in ps),
            })
    return units


def team_exposure(P, phase):
    GPS = 2.4  # games per Bo3 series
    exp = {}
    for t, p in P.items():
        series = (4 * p["4-0"] + 5 * p["4-1"] + 6 * p["elim_win"]
                  + 6 * p["elim_lose"] + 5 * p["1-4"] + 4 * p["0-4"])
        group_games = series * GPS
        if phase == "group":
            exp[t] = group_games
        else:
            playoff = p["4-0"] + p["4-1"] + p["elim_win"]
            exp[t] = group_games + playoff * 3 * GPS
    return exp


def fmt_emblems(emblems):
    return " + ".join(f"{e['label']}[{e['color']}]{e['value']}" for e in emblems)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["group", "main"], default="main")
    ap.add_argument("--metric", choices=["avg", "top"], default="avg")
    ap.add_argument("--emblems", type=int, default=3)
    ap.add_argument("--sims", type=int, default=120000)
    args = ap.parse_args()

    players = load_players()
    units = build_units(players, args.metric, args.emblems)

    P, playoffs = compute_probs(N=args.sims)
    P = {SIM_TO_DATA[t]: v for t, v in P.items()}
    playoffs = {SIM_TO_DATA[t]: v for t, v in playoffs.items()}
    exposure = team_exposure(P, args.phase)
    mean_exp = sum(exposure.values()) / len(exposure)
    weight = {t: exposure[t] / mean_exp for t in exposure}

    for role in units:
        for u in units[role]:
            u["weight"] = weight.get(u["team"], 1.0)
            u["playoff"] = playoffs.get(u["team"], 0.0)
            u["ev"] = u["score"] * u["weight"]

    metric_lbl = "AVG" if args.metric == "avg" else "TOP"
    print("\n=== TI15 FANTASY PICK LAYER (rules-accurate) ===")
    print(f"phase={args.phase}  metric={metric_lbl}  emblems={args.emblems}  sims={args.sims:,}")
    print("score = best-3 emblem points (of 18) ; EV = score x team game-weight")
    print("colors: [R]ed [B]lue [G]reen\n")

    role_names = {"core": "CORE (2 гравці, пара)", "mid": "MID (1 гравець)",
                  "support": "SUPPORT (2 гравці, пара)"}
    report = {"phase": args.phase, "metric": args.metric,
              "emblems": args.emblems, "roles": {}}
    for role in ("core", "mid", "support"):
        ranked = sorted(units[role], key=lambda x: -x["ev"])
        print(f"----- {role_names[role]} -----")
        for i, u in enumerate(ranked, 1):
            note = "" if u["min_games"] >= 40 else f"  ⚠ {u['min_games']:.0f} ігор"
            print(f"{i:>2}. {u['team']:<18} {'/'.join(u['players']):<24}"
                  f" score={u['score']:>5.0f} wt={u['weight']:.2f} PO={u['playoff']*100:>3.0f}%"
                  f" EV={u['ev']:>5.0f}{note}")
            print(f"     емблеми: {fmt_emblems(u['emblems'])}")
        print()
        report["roles"][role] = ranked

    best = {r: max(units[r], key=lambda x: x["ev"]) for r in units}
    print("=== РЕКОМЕНДОВАНИЙ СКЛАД ===")
    total = 0.0
    for role in ("core", "mid", "support"):
        u = best[role]
        total += u["ev"]
        print(f"  {role.upper():<8} {'/'.join(u['players']):<24} ({u['team']})  EV={u['ev']:.0f}")
        print(f"           ставити емблеми: {fmt_emblems(u['emblems'])}")
    print(f"  РАЗОМ EV ≈ {total:.0f}")
    report["recommended"] = {r: best[r] for r in best}

    with open(os.path.join(BASE, "recommendation.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
