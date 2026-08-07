"""
Account-aware fantasy pick (screenshot → table).

Flow:
  1. Update fantasy/account_state.json from screenshots
     (current team + 3 emblems with final % per slot).
  2. Run:  python fantasy/account.py
  3. Read fantasy/account_pick.md  (script output, not invented).

Score per slot:
    AVG/TOP = sum( player_stat * emblem_pct / 100 )
    EV      = AVG * team_weight_from_prediction
where team_weight comes from ti15_swiss_sim (phase=group|main).
"""
import argparse
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.dirname(BASE))
from optimize import SIM_TO_DATA, team_exposure, unit_char_values  # noqa: E402
from ti15_swiss_sim import compute_probs  # noqa: E402

STATE_PATH = os.path.join(BASE, "account_state.json")
OUT_PATH = os.path.join(BASE, "account_pick.md")
MIN_GAMES = 40

LABEL = {
    "gpm": "ЗЗХ", "roshan": "Рошан", "deaths": "Смерті", "creeps": "Кріпи",
    "runes": "Руни", "tormentor": "Мучителі", "smokes": "Дими",
    "teamfight": "Тімфайти", "lotuses": "Лотоси", "kills": "Вбивства",
    "towers": "Вежі", "madstone": "Лютит", "wards": "Варди", "camps": "Табори",
    "watchers": "Споглядачі", "stuns": "Стани", "fb": "Перша кров",
    "courier": "Кур'єри",
}
ROLE_LBL = {"core": "CORE", "mid": "MID", "support": "SUPPORT"}


def load_state():
    with open(STATE_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_players():
    with open(os.path.join(BASE, "players.json"), encoding="utf-8") as f:
        return json.load(f)


def group(players):
    teams = {}
    for p in players:
        teams.setdefault(p["team"], {"core": [], "mid": [], "support": []})
        teams[p["team"]][p.get("role", "core")].append(p)
    return teams


def emblems_tuples(slot):
    return [(e["stat"], e["pct"]) for e in slot["emblems"]]


def slot_score(ps, emblems, metric):
    vals = unit_char_values(ps, metric)
    return sum(vals[key] * pct / 100.0 for key, pct in emblems)


def emblem_str(emblems):
    return " + ".join(f"{LABEL.get(k, k)} {p}%" for k, p in emblems)


def rank_slot(teams, role, emblems, cur_team, weight, playoffs):
    cands = []
    for team, roles in teams.items():
        if not roles[role]:
            continue
        avg = slot_score(roles[role], emblems, "avg")
        top = slot_score(roles[role], emblems, "top")
        wt = weight.get(team, 1.0)
        cands.append({
            "team": team,
            "players": "/".join(p["name"] for p in roles[role]),
            "avg": avg,
            "top": top,
            "wt": wt,
            "po": playoffs.get(team, 0.0),
            "ev": avg * wt,
            "min_games": min(p["gamesPlayed"] for p in roles[role]),
            "is_current": team == cur_team,
        })
    cands.sort(key=lambda x: -x["ev"])
    reliable = [c for c in cands if c["min_games"] >= MIN_GAMES] or cands
    best = max(reliable, key=lambda x: x["ev"])
    cur = next((c for c in cands if c["is_current"]), None)
    return cands, best, cur


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sims", type=int, default=120000)
    ap.add_argument("--state", default=STATE_PATH)
    args = ap.parse_args()

    with open(args.state, encoding="utf-8") as f:
        state = json.load(f)
    phase = state.get("phase", "group")
    name = state.get("name", "account")
    slots = state["slots"]

    teams = group(load_players())
    P, playoffs = compute_probs(N=args.sims)
    P = {SIM_TO_DATA[t]: v for t, v in P.items()}
    playoffs = {SIM_TO_DATA[t]: v for t, v in playoffs.items()}
    exp = team_exposure(P, phase)
    mean = sum(exp.values()) / len(exp)
    weight = {t: exp[t] / mean for t in exp}

    lines = [
        f"# Account table — **{name}**",
        "",
        f"Джерело стану: `account_state.json` · фаза: `{phase}` · "
        f"симуляція: {args.sims:,} · поріг надійності: ≥{MIN_GAMES} ігор.",
        "",
        "Формула: `AVG/TOP = Σ(стат × %емблеми/100)` · `EV = AVG × вага_команди(прогноз)`.",
        "",
        "## Підсумок (скрипт)",
        "",
        "| Роль | Емблеми | Зараз | Рекомендація | AVG зараз | AVG рек. | TOP рек. | EV зараз | EV рек. | Дія |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---|",
    ]

    details = []
    tot_cur_avg = tot_cur_top = 0.0
    tot_best_avg = tot_best_top = 0.0

    for role in ("core", "mid", "support"):
        slot = slots[role]
        emb = emblems_tuples(slot)
        cands, best, cur = rank_slot(
            teams, role, emb, slot["team"], weight, playoffs
        )
        if cur is None:
            raise SystemExit(f"current team '{slot['team']}' not found for {role}")

        keep = best["team"] == cur["team"]
        action = "лишити" if keep else f"замінити → {best['team']}"
        lines.append(
            f"| {ROLE_LBL[role]} | {emblem_str(emb)} | "
            f"{cur['players']} ({cur['team']}) | "
            f"{best['players']} ({best['team']}) | "
            f"{cur['avg']:.0f} | {best['avg']:.0f} | {best['top']:.0f} | "
            f"{cur['ev']:.0f} | {best['ev']:.0f} | {action} |"
        )
        # TOTAL = чиста статистика (під емблеми), без ваги прогнозу
        tot_cur_avg += cur["avg"]
        tot_cur_top += cur["top"]
        tot_best_avg += best["avg"]
        tot_best_top += best["top"]

        block = [
            "",
            f"## {ROLE_LBL[role]} — {emblem_str(emb)}",
            "",
            "| # | Команда | Гравці | AVG | TOP | wt | PO% | EV |",
            "|--:|---|---|--:|--:|--:|--:|--:|",
        ]
        for i, c in enumerate(cands, 1):
            mark = " ← ТИ" if c["is_current"] else ""
            warn = " ⚠" if c["min_games"] < MIN_GAMES else ""
            star = " ★" if c["team"] == best["team"] else ""
            block.append(
                f"| {i} | {c['team']}{warn}{mark}{star} | {c['players']} | "
                f"{c['avg']:.0f} | {c['top']:.0f} | {c['wt']:.2f} | "
                f"{c['po']*100:.0f}% | {c['ev']:.0f} |"
            )
        if keep:
            block.append("")
            block.append(
                f"**Скрипт:** лишити {cur['players']} ({cur['team']}) — "
                f"найкращий надійний EV під ці емблеми."
            )
        else:
            d = best["ev"] - cur["ev"]
            block.append("")
            block.append(
                f"**Скрипт:** {cur['players']} ({cur['team']}, EV {cur['ev']:.0f}) → "
                f"**{best['players']} ({best['team']}, EV {best['ev']:.0f})**, "
                f"+{d:.0f} EV (AVG {cur['avg']:.0f}→{best['avg']:.0f})."
            )
        details.extend(block)

    lines.append(
        f"| **TOTAL** | *(лише стат гравця × %емблем, без прогнозу)* | "
        f"поточний | **рекомендований** | "
        f"**{tot_cur_avg:.0f}** | **{tot_best_avg:.0f}** | **{tot_best_top:.0f}** | "
        f"— | — | |"
    )
    lines.append("")
    lines.append(
        f"**TOTAL якщо виставити рекомендованих (без прогнозу):** "
        f"AVG **{tot_best_avg:.0f}** · MAX **{tot_best_top:.0f}** "
        f"(зараз: AVG {tot_cur_avg:.0f} · MAX {tot_cur_top:.0f})."
    )
    lines.extend(details)
    lines.append("")
    text = "\n".join(lines) + "\n"
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)
    print(f"[written] {OUT_PATH}")


if __name__ == "__main__":
    main()
