"""
TI15 (The International 2026) Swiss Stage Monte Carlo
=====================================================
Implements Valve's published TI15 group-stage rules:
  - 16 teams, all Bo3, run until 4 wins (advance) or 4 losses (out)
  - R1: two pre-assigned groups of 8, pairings inside group
  - R2-R3: same record AND same initial group, minimise seed gap
  - R4: same record, CROSS-group, minimise seed gap
  - R5: same record, maximise seed gap
  - Final buckets: 4-0 (1), 4-1 (2), 3-2 (5), 2-3 (5), 1-4 (2), 0-4 (1)
  - Elimination Round: each 3-2 team picks a 2-3 opponent, best Swiss
    standing picks first (rational pick = weakest available opponent)
Ratings are analyst-set Elo (base = dota2protips ELO @ 29 Jun 2026,
updated for EWC 2026 results + TI-specific adjustments).
"""
import random
from itertools import combinations

# ---------------------------------------------------------------- ratings
RATING = {
    "Team Vision":     1770,  # PARIVISION: EWC + DreamLeague S29 champ, Puppey
    "Team Yandex":     1702,  # EWC 3rd, BLAST Slam VII / Wallachia S7 / DL S27
    "BoomBoys":        1678,  # BetBoom: EWC runner-up
    "Team Falcons":    1655,  # TI14 champs, EWC 5-8, slow patch fits
    "Team Spirit":     1617,  # 2x TI champs, EWC 5-8, uneven season
    "Aurora Gaming":   1575,  # serial runner-up, but EWC 9-12
    "Vici Gaming":     1561,  # EWC 4th, best current CN form
    "Team Liquid":     1538,  # EWC 9-12, 5 events w/o a final
    "Nigma Galaxy":    1530,  # EWC 5-8, SumaiL, late-game meta fit
    "LGD Gaming":      1528,  # BLAST Slam VII 2nd, dominant SA qualifier
    "1win Team":       1526,  # ex-Tundra roster, TI pedigree, poor form
    "Team Resilience": 1515,  # 12 series as a roster, undefeated CN qual
    "Xtreme Gaming":   1455,  # TI14 finalists but EWC 13-16, unstable
    "GamerLegion":     1400,  # weak NA region, EWC 17-20
    "OG":              1388,  # SEA qual winner, EWC 17-20
    "HULIGANI":        1367,  # L1GA, EWC 21-24
}
TEAMS = sorted(RATING, key=lambda t: -RATING[t])
SEED = {t: i for i, t in enumerate(TEAMS)}          # 0 = top seed
# snake-seeded pre-assigned groups of 8 (seeds are 0-indexed)
GROUP = {}
for s, t in enumerate(TEAMS):
    GROUP[t] = 0 if s % 4 in (0, 3) else 1          # 1,4,5,8,... vs 2,3,6,7,...

DIVISOR = 600.0   # compressed Elo scale: Dota upsets are common

def p_game(a, b):
    return 1.0 / (1.0 + 10 ** (-(RATING[a] - RATING[b]) / DIVISOR))

def p_bo3(a, b):
    p = p_game(a, b)
    return p * p * (3 - 2 * p)

PBO3 = {(a, b): p_bo3(a, b) for a in TEAMS for b in TEAMS if a != b}


def pair_bucket(bucket, played, mode, rnd):
    """Pair teams within one record bucket.
    mode 'min' -> minimise seed gap, 'max' -> maximise seed gap.
    Avoids rematches when possible. Exhaustive over perfect matchings
    (bucket size <= 8, so at most 105 matchings)."""
    bucket = sorted(bucket, key=lambda t: SEED[t])
    n = len(bucket)
    if n == 0:
        return []
    if n == 2:
        return [(bucket[0], bucket[1])]

    best, best_key = None, None
    for matching in perfect_matchings(bucket):
        rematches = sum(1 for a, b in matching if b in played[a])
        gap = sum(abs(SEED[a] - SEED[b]) for a, b in matching)
        key = (rematches, gap if mode == "min" else -gap)
        if best_key is None or key < best_key:
            best_key, best = key, matching
    return best


_MATCH_CACHE = {}
def perfect_matchings(items):
    items = tuple(items)
    if len(items) <= 1:
        return [[]]
    if items in _MATCH_CACHE:
        return _MATCH_CACHE[items]
    out = []
    first, rest = items[0], items[1:]
    for i, other in enumerate(rest):
        remainder = rest[:i] + rest[i + 1:]
        for sub in perfect_matchings(remainder):
            out.append([(first, other)] + sub)
    _MATCH_CACHE[items] = out
    return out


def play(a, b, rng):
    return (a, b) if rng.random() < PBO3[(a, b)] else (b, a)


def simulate(rng):
    w = {t: 0 for t in TEAMS}
    l = {t: 0 for t in TEAMS}
    played = {t: set() for t in TEAMS}

    for rnd in range(1, 6):
        active = [t for t in TEAMS if w[t] < 4 and l[t] < 4]
        # bucket key: record, plus initial group for rounds 1-3
        buckets = {}
        for t in active:
            key = (w[t], l[t], GROUP[t] if rnd <= 3 else 0)
            buckets.setdefault(key, []).append(t)

        mode = "max" if rnd == 5 else "min"
        for key, bucket in buckets.items():
            if rnd == 1:
                # inside each group of 8: top half vs bottom half (1v5,2v6,...)
                b = sorted(bucket, key=lambda t: SEED[t])
                half = len(b) // 2
                pairs = list(zip(b[:half], b[half:]))
            else:
                pairs = pair_bucket(bucket, played, mode, rnd)
            for a, b in pairs:
                win, lose = play(a, b, rng)
                w[win] += 1
                l[lose] += 1
                played[a].add(b)
                played[b].add(a)

    rec = {t: (w[t], l[t]) for t in TEAMS}
    top32 = sorted([t for t in TEAMS if rec[t] == (3, 2)], key=lambda t: SEED[t])
    pool23 = [t for t in TEAMS if rec[t] == (2, 3)]

    # elimination round: 3-2 teams pick weakest remaining 2-3 opponent
    elim_win, elim_lose = [], []
    avail = sorted(pool23, key=lambda t: RATING[t])
    for picker in top32:
        opp = avail.pop(0)
        win, lose = play(picker, opp, rng)
        elim_win.append(win)
        elim_lose.append(lose)
    return rec, elim_win, elim_lose


def main(N=300000, seed=12345):
    rng = random.Random(seed)
    cats = ["4-0", "4-1", "elim_win", "elim_lose", "1-4", "0-4"]
    cnt = {t: {c: 0 for c in cats} for t in TEAMS}
    playoffs = {t: 0 for t in TEAMS}
    for _ in range(N):
        rec, ew, el = simulate(rng)
        for t in TEAMS:
            r = rec[t]
            if r == (4, 0):
                cnt[t]["4-0"] += 1; playoffs[t] += 1
            elif r == (4, 1):
                cnt[t]["4-1"] += 1; playoffs[t] += 1
            elif r == (1, 4):
                cnt[t]["1-4"] += 1
            elif r == (0, 4):
                cnt[t]["0-4"] += 1
        for t in ew:
            cnt[t]["elim_win"] += 1; playoffs[t] += 1
        for t in el:
            cnt[t]["elim_lose"] += 1

    P = {t: {c: cnt[t][c] / N for c in cats} for t in TEAMS}
    print(f"N = {N} simulations, Elo divisor {DIVISOR:.0f}\n")
    hdr = f"{'team':<17}{'rating':>7}{'4-0':>8}{'4-1':>8}{'ElimW':>8}{'ElimL':>8}{'1-4':>8}{'0-4':>8}{'PLAYOFF':>9}"
    print(hdr); print("-" * len(hdr))
    for t in TEAMS:
        p = P[t]
        print(f"{t:<17}{RATING[t]:>7}"
              f"{p['4-0']*100:>7.1f}%{p['4-1']*100:>7.1f}%{p['elim_win']*100:>7.1f}%"
              f"{p['elim_lose']*100:>7.1f}%{p['1-4']*100:>7.1f}%{p['0-4']*100:>7.1f}%"
              f"{playoffs[t]/N*100:>8.1f}%")

    # ---- EV-optimal pick'em assignment (slot counts fixed by format) ----
    slots = ["4-0"] + ["4-1"] * 2 + ["elim_win"] * 5 + ["elim_lose"] * 5 + ["1-4"] * 2 + ["0-4"]
    best_val, best_asg = -1, None
    for start in range(4000):
        r2 = random.Random(start)
        order = TEAMS[:]
        if start:
            r2.shuffle(order)
        asg = dict(zip(order, slots))
        improved = True
        while improved:
            improved = False
            for a, b in combinations(TEAMS, 2):
                if asg[a] == asg[b]:
                    continue
                cur = P[a][asg[a]] + P[b][asg[b]]
                new = P[a][asg[b]] + P[b][asg[a]]
                if new > cur + 1e-12:
                    asg[a], asg[b] = asg[b], asg[a]
                    improved = True
        val = sum(P[t][asg[t]] for t in TEAMS)
        if val > best_val:
            best_val, best_asg = val, dict(asg)

    print(f"\nEV-optimal pick'em -- expected correct slots: {best_val:.2f} / 16\n")
    for c in cats:
        picks = sorted([t for t in TEAMS if best_asg[t] == c], key=lambda t: -P[t][c])
        print(f"{c:<10} " + ", ".join(f"{t} ({P[t][c]*100:.0f}%)" for t in picks))

    print("\nfull probability matrix (for confidence scoring)")
    for t in TEAMS:
        print(t, {c: round(P[t][c] * 100, 1) for c in cats})


if __name__ == "__main__":
    main()
