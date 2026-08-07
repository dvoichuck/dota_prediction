"""
Build nickname | AVG | MAX table for recommended lineups.

Reads every fantasy/accounts/*.json, computes recommended Core/Mid/Support
under that account's emblems, sums AVG and MAX (player stats × emblem %,
NO prediction weight), writes fantasy/totals.md.

Run:  python fantasy/totals.py
"""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.dirname(BASE))

from account import (  # noqa: E402
    MIN_GAMES, emblems_tuples, group, load_players, rank_slot,
)
from optimize import SIM_TO_DATA, team_exposure  # noqa: E402
from ti15_swiss_sim import compute_probs  # noqa: E402

ACCOUNTS_DIR = os.path.join(BASE, "accounts")
OUT_PATH = os.path.join(BASE, "totals.md")


def recommended_totals(state, teams, weight, playoffs):
    tot_avg = tot_max = 0.0
    picks = []
    for role in ("core", "mid", "support"):
        slot = state["slots"][role]
        emb = emblems_tuples(slot)
        _cands, best, _cur = rank_slot(
            teams, role, emb, slot["team"], weight, playoffs
        )
        tot_avg += best["avg"]
        tot_max += best["top"]
        picks.append(f"{best['players']} ({best['team']})")
    return tot_avg, tot_max, picks


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--sims", type=int, default=80000)
    args = ap.parse_args()

    files = sorted(
        f for f in os.listdir(ACCOUNTS_DIR) if f.endswith(".json")
    )
    if not files:
        raise SystemExit(f"no account JSON in {ACCOUNTS_DIR}")

    players = load_players()
    teams = group(players)

    # one sim run; phase can differ per account
    cache = {}

    def get_weights(phase):
        if phase not in cache:
            P, playoffs = compute_probs(N=args.sims)
            P = {SIM_TO_DATA[t]: v for t, v in P.items()}
            playoffs = {SIM_TO_DATA[t]: v for t, v in playoffs.items()}
            exp = team_exposure(P, phase)
            mean = sum(exp.values()) / len(exp)
            weight = {t: exp[t] / mean for t in exp}
            cache[phase] = (weight, playoffs)
        return cache[phase]

    rows = []
    for fname in files:
        with open(os.path.join(ACCOUNTS_DIR, fname), encoding="utf-8") as f:
            state = json.load(f)
        phase = state.get("phase", "group")
        weight, playoffs = get_weights(phase)
        avg, mx, picks = recommended_totals(state, teams, weight, playoffs)
        rows.append({
            "name": state.get("name", fname),
            "avg": avg,
            "max": mx,
            "picks": picks,
            "phase": phase,
        })

    rows.sort(key=lambda r: -r["avg"])

    lines = [
        "# Fantasy totals (рекомендований склад)",
        "",
        "AVG / MAX = сума Core+Mid+Support під емблеми акаунта "
        "(стат × %, **без** ваги прогнозу). Підбір гравців — EV з прогнозом.",
        "",
        "| nickname | AVG | MAX |",
        "|---|---:|---:|",
    ]
    for r in rows:
        lines.append(f"| {r['name']} | {r['avg']:.0f} | {r['max']:.0f} |")
    lines.append("")
    lines.append("## Рекомендовані гравці")
    lines.append("")
    for r in rows:
        lines.append(f"- **{r['name']}:** Core {r['picks'][0]} · Mid {r['picks'][1]} · Support {r['picks'][2]}")
    lines.append("")

    text = "\n".join(lines)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)
    print(f"[written] {OUT_PATH}")


if __name__ == "__main__":
    main()
