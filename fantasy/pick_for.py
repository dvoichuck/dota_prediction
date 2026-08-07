"""
Pick an optimal fantasy lineup for a given account and write a markdown
table with the AVERAGE and MAXIMUM fantasy value of the chosen team.

Value convention (matches the emblems you actually equip):
  * emblems are chosen by best-3 AVERAGE points (of 18 characteristics)
  * unit "середнє" (AVG) = sum of those emblems' per-game average points
  * unit "максимум" (TOP) = sum of those same emblems' ceiling points
Team weight comes from the Monte-Carlo advancement odds (phase=main).

Run:  python fantasy/pick_for.py --name Lanos
"""
import argparse
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.dirname(BASE))
from optimize import (CHARS, SIM_TO_DATA, team_exposure,  # noqa: E402
                      best_emblems, unit_char_values)
from ti15_swiss_sim import compute_probs  # noqa: E402


def load_players():
    with open(os.path.join(BASE, "players.json"), "r", encoding="utf-8") as f:
        return json.load(f)


def group(players):
    teams = {}
    for p in players:
        teams.setdefault(p["team"], {"core": [], "mid": [], "support": []})
        teams[p["team"]][p.get("role", "core")].append(p)
    return teams


def unit_record(ps, n_emblems):
    avg = unit_char_values(ps, "avg")
    top = unit_char_values(ps, "top")
    _score, chosen = best_emblems(avg, n_emblems)   # pick emblems by average
    keys = [c[0] for c in chosen]
    return {
        "players": [p["name"] for p in ps],
        "emblems": chosen,
        "avg": sum(avg[k] for k in keys),
        "top": sum(top[k] for k in keys),
        "min_games": min(p["gamesPlayed"] for p in ps),
    }


def fmt_emblems(chosen):
    return " + ".join(f"{l}[{c}]" for _k, c, l in chosen)


MIN_GAMES = 40   # reliability floor: don't recommend tiny-sample units


def best_per_role(teams, weight, playoffs, n_emblems, guard=True):
    best = {}
    for role in ("core", "mid", "support"):
        cands = []
        for team, roles in teams.items():
            if not roles[role]:
                continue
            rec = unit_record(roles[role], n_emblems)
            rec["team"] = team
            rec["weight"] = weight.get(team, 1.0)
            rec["playoff"] = playoffs.get(team, 0.0)
            rec["ev"] = rec["avg"] * rec["weight"]
            cands.append(rec)
        pool = [c for c in cands if c["min_games"] >= MIN_GAMES] if guard else cands
        pool = pool or cands
        best[role] = max(pool, key=lambda x: x["ev"])
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="Lanos")
    ap.add_argument("--phase", choices=["group", "main"], default="group")
    ap.add_argument("--emblems", type=int, default=3)
    ap.add_argument("--sims", type=int, default=120000)
    args = ap.parse_args()

    players = load_players()
    teams = group(players)

    P, playoffs = compute_probs(N=args.sims)
    P = {SIM_TO_DATA[t]: v for t, v in P.items()}
    playoffs = {SIM_TO_DATA[t]: v for t, v in playoffs.items()}

    def weights_for(phase):
        exp = team_exposure(P, phase)
        m = sum(exp.values()) / len(exp)
        return {t: exp[t] / m for t in exp}

    best = best_per_role(teams, weights_for(args.phase), playoffs, args.emblems)
    best_main = best_per_role(teams, weights_for("main"), playoffs, args.emblems)

    # his current lineup (from the screenshot)
    current = {"core": "LGD Gaming", "mid": "Team Liquid", "support": "LGD Gaming"}
    cur = {}
    for role, team in current.items():
        rec = unit_record(teams[team][role], args.emblems)
        rec["team"] = team
        rec["playoff"] = playoffs.get(team, 0.0)
        cur[role] = rec

    role_lbl = {"core": "CORE", "mid": "MID", "support": "SUPPORT"}

    def table(units_by_role):
        rows = ["| Роль | Команда | Гравці | Емблеми | AVG | TOP | PO% |",
                "|---|---|---|---|---:|---:|---:|"]
        ta = tt = 0
        for role in ("core", "mid", "support"):
            u = units_by_role[role]
            ta += u["avg"]; tt += u["top"]
            note = "" if u["min_games"] >= MIN_GAMES else " ⚠"
            rows.append(f"| {role_lbl[role]} | {u['team']}{note} | {'/'.join(u['players'])} | "
                        f"{fmt_emblems(u['emblems'])} | {u['avg']:.0f} | {u['top']:.0f} | {u['playoff']*100:.0f}% |")
        rows.append(f"| **РАЗОМ** | | | | **{ta:.0f}** | **{tt:.0f}** | |")
        return rows, ta, tt

    phase_lbl = "груповий етап (цей період)" if args.phase == "group" else "плейоф / глибокий прохід"
    lines = []
    lines.append(f"# Фентезі-підбір для **{args.name}**")
    lines.append("")
    lines.append(f"Оптимізація під: **{phase_lbl}** · емблем на стягу: {args.emblems} · "
                 f"симуляція: {args.sims:,} прогонів.")
    lines.append("Значення = сума **обраних 3 емблем**. "
                 "**AVG** = середні очки/гра, **TOP** = стеля (найкраща гра). "
                 "`PO%` = шанс виходу в плейоф (наш прогноз). ⚠ = мала вибірка ігор.")
    lines.append("")
    lines.append(f"> На груповому етапі всі команди грають ~5 серій, тож загальні очки ≈ очки/гру — "
                 f"вирішує **чиста фентезі-сила**, а не глибина плейофу. Тому головний підбір рахований "
                 f"під груповий етап; окремо нижче — варіант під плейоф.")
    lines.append("")
    lines.append("## Рекомендований склад (груповий етап)")
    lines.append("")
    rows, tot_avg, tot_top = table(best)
    lines += rows
    lines.append("")

    lines.append("## Поточний склад Ланоса (для порівняння)")
    lines.append("")
    lines.append("Емблеми оптимізовано (best-3), щоб порівнювати саме вибір гравців.")
    lines.append("")
    rows, cur_avg, cur_top = table(cur)
    lines += rows
    lines.append("")
    d_avg = tot_avg - cur_avg
    d_top = tot_top - cur_top
    lines.append(f"**Різниця рекомендованого проти поточного:** AVG {d_avg:+.0f} "
                 f"({d_avg/cur_avg*100:+.1f}%) · TOP {d_top:+.0f} ({d_top/cur_top*100:+.1f}%).")
    lines.append("")
    lines.append("### Порада по кожній ролі (груповий етап)")
    for role in ("core", "mid", "support"):
        c, b = cur[role], best[role]
        if c["team"] == b["team"] and c["players"] == b["players"]:
            lines.append(f"- **{role_lbl[role]}:** лишити {'/'.join(c['players'])} ({c['team']}) — вже оптимально.")
        else:
            diff = b["avg"] - c["avg"]
            verb = "невеликий апгрейд" if diff < 200 else "апгрейд"
            lines.append(f"- **{role_lbl[role]}:** {'/'.join(c['players'])} ({c['team']}, AVG {c['avg']:.0f}) "
                         f"→ {'/'.join(b['players'])} ({b['team']}, AVG {b['avg']:.0f}) — {verb} {diff:+.0f} AVG.")
    lines.append("")
    lines.append("## Альтернатива під плейоф (якщо оптимізуєш період The International)")
    lines.append("")
    lines.append("Тут фаворити важать сильно (більше ігор у плейофі).")
    lines.append("")
    rows, _ma, _mt = table(best_main)
    lines += rows
    text = "\n".join(lines) + "\n"
    out = os.path.join(BASE, f"pick_{args.name.lower()}.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)
    print(f"\n[written] {out}")


if __name__ == "__main__":
    main()
