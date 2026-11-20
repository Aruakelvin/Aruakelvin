"""Dixon-Coles football model with time decay, blended with bookmaker odds.

Usage:
    python -m football_predictor.model --data DIR [--league PL|CH|L1|LL|LL2] [--asof 2026-11-20] [--backtest]

DIR holds openfootball JSON files (en1_*.json = Premier League,
en2_*.json = Championship, en3_*.json = League One,
en4_*.json = League Two,
es1_*.json = LaLiga, es2_*.json = LaLiga 2). Fixtures and odds live in fixtures.py.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import re
from dataclasses import dataclass
from datetime import date

import numpy as np
from scipy.optimize import minimize
from scipy.stats import poisson

MAX_GOALS = 10
HALF_LIFE_DAYS = 240  # weight of a match halves every ~8 months


@dataclass
class Match:
    day: date
    home: str
    away: str
    hg: int
    ag: int
    league: str


LEAGUE_FILES = {"en1": "PL", "en2": "CH", "en3": "L1", "en4": "L2", "es1": "LL", "es2": "LL2"}
COUNTRY = {"PL": "en", "CH": "en", "L1": "en", "LL": "es", "LL2": "es"}

# Same club, different spelling between files (after norm()).
ALIASES = {
    "RC Deportivo La Coruña": "Deportivo La Coruña",
    "Real Racing Club de Santander": "Racing Santander",
    "Real Valladolid CF": "Real Valladolid",
}


def norm(team: str) -> str:
    """Make names consistent across files: 'Bolton Wanderers FC' == 'Bolton Wanderers'."""
    team = re.sub(r" A?FC$", "", team.strip())
    return ALIASES.get(team, team)


def load_matches(data_dir: str, country: str = "en") -> list[Match]:
    out = []
    for path in sorted(glob.glob(os.path.join(data_dir, f"{country}[1-4]_*.json"))):
        league = LEAGUE_FILES[os.path.basename(path)[:3]]
        for m in json.load(open(path))["matches"]:
            score = m.get("score")
            ft = score.get("ft") if isinstance(score, dict) else None
            if not ft:
                continue
            out.append(Match(date.fromisoformat(m["date"]), norm(m["team1"]), norm(m["team2"]),
                             int(ft[0]), int(ft[1]), league))
    return sorted(out, key=lambda x: x.day)


def _tau(x, y, lam, mu, rho):
    """Dixon-Coles low-score correction."""
    if x == 0 and y == 0:
        return 1 - lam * mu * rho
    if x == 0 and y == 1:
        return 1 + lam * rho
    if x == 1 and y == 0:
        return 1 + mu * rho
    if x == 1 and y == 1:
        return 1 - rho
    return 1.0


class DixonColes:
    def fit(self, matches: list[Match], asof: date):
        teams = sorted({m.home for m in matches} | {m.away for m in matches})
        idx = {t: i for i, t in enumerate(teams)}
        n = len(teams)
        h = np.array([idx[m.home] for m in matches])
        a = np.array([idx[m.away] for m in matches])
        hg = np.array([m.hg for m in matches])
        ag = np.array([m.ag for m in matches])
        age = np.array([(asof - m.day).days for m in matches])
        w = 0.5 ** (age / HALF_LIFE_DAYS)
        low = (hg <= 1) & (ag <= 1)

        def nll(p):
            att = p[:n]
            dfn = p[n:2 * n]
            home_adv, rho = p[2 * n], p[2 * n + 1]
            lam = np.exp(att[h] + dfn[a] + home_adv)
            mu = np.exp(att[a] + dfn[h])
            ll = hg * np.log(lam) - lam + ag * np.log(mu) - mu
            tau = np.ones_like(lam)
            tau = np.where((hg == 0) & (ag == 0), 1 - lam * mu * rho, tau)
            tau = np.where((hg == 0) & (ag == 1), 1 + lam * rho, tau)
            tau = np.where((hg == 1) & (ag == 0), 1 + mu * rho, tau)
            tau = np.where((hg == 1) & (ag == 1), 1 - rho, tau)
            ll = ll + np.where(low, np.log(np.clip(tau, 1e-10, None)), 0)
            # small ridge keeps sparse teams sensible; sum(att)=0 for identifiability
            return -(w * ll).sum() + 0.5 * (att.sum() ** 2) + 0.01 * (att ** 2 + dfn ** 2).sum()

        p0 = np.concatenate([np.zeros(2 * n), [0.25, -0.05]])
        bounds = [(-3, 3)] * (2 * n) + [(-1, 1), (-0.3, 0.3)]
        res = minimize(nll, p0, method="L-BFGS-B", bounds=bounds)
        self.teams, self.idx = teams, idx
        self.att, self.dfn = res.x[:n], res.x[n:2 * n]
        self.home_adv, self.rho = res.x[2 * n], res.x[2 * n + 1]
        return self

    def expected_goals(self, home: str, away: str):
        i, j = self.idx[home], self.idx[away]
        lam = math.exp(self.att[i] + self.dfn[j] + self.home_adv)
        mu = math.exp(self.att[j] + self.dfn[i])
        return lam, mu

    def score_matrix(self, home: str, away: str) -> np.ndarray:
        lam, mu = self.expected_goals(home, away)
        g = np.arange(MAX_GOALS + 1)
        mat = np.outer(poisson.pmf(g, lam), poisson.pmf(g, mu))
        for x in (0, 1):
            for y in (0, 1):
                mat[x, y] *= _tau(x, y, lam, mu, self.rho)
        return mat / mat.sum()


def outcome_probs(mat: np.ndarray):
    return np.tril(mat, -1).sum(), np.trace(mat), np.triu(mat, 1).sum()


def markets(mat: np.ndarray) -> dict:
    g = np.arange(MAX_GOALS + 1)
    total = g[:, None] + g[None, :]
    p1, px, p2 = outcome_probs(mat)
    top = np.dstack(np.unravel_index(np.argsort(mat.ravel())[::-1][:3], mat.shape))[0]
    return {
        "1": p1, "X": px, "2": p2,
        "O2.5": mat[total > 2.5].sum(),
        "GG": mat[1:, 1:].sum(),
        "scores": [(f"{x}-{y}", mat[x, y]) for x, y in top],
    }


def devig(odds: tuple[float, float, float]) -> np.ndarray:
    """Turn 1X2 odds into probabilities, removing the bookmaker margin proportionally."""
    inv = np.array([1 / o for o in odds])
    return inv / inv.sum()


def backtest(matches: list[Match], start: date, end: date, league: str = "PL", refit_days: int = 14):
    """Walk forward through one league's matches in [start, end), refitting every refit_days."""
    pl = [m for m in matches if m.league == league and start <= m.day < end]
    correct = n = 0
    brier = logloss = 0.0
    cut = start
    model = None
    for m in pl:
        if model is None or (m.day - cut).days >= refit_days:
            cut = m.day
            model = DixonColes().fit([x for x in matches if x.day < cut], cut)
        if m.home not in model.idx or m.away not in model.idx:
            continue
        p = np.array(outcome_probs(model.score_matrix(m.home, m.away)))
        actual = 0 if m.hg > m.ag else (1 if m.hg == m.ag else 2)
        y = np.eye(3)[actual]
        correct += int(p.argmax() == actual)
        brier += ((p - y) ** 2).sum()
        logloss += -math.log(p[actual])
        n += 1
    return {"matches": n, "accuracy": correct / n, "brier": brier / n, "logloss": logloss / n}


def main():
    from football_predictor.fixtures import FIXTURES, MARKET_WEIGHT


    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--asof", default=date.today().isoformat())
    ap.add_argument("--league", default="PL", choices=sorted(FIXTURES))
    ap.add_argument("--backtest", action="store_true")
    args = ap.parse_args()
    asof = date.fromisoformat(args.asof)
    matches = load_matches(args.data, COUNTRY[args.league])
    print(f"Loaded {len(matches)} matches, last result {matches[-1].day}")

    if args.backtest:
        r = backtest(matches, date(2025, 8, 1), date(2026, 6, 1), args.league)
        print(f"Backtest 2025-26 {args.league}: {r['matches']} matches, accuracy {r['accuracy']:.1%}, "
              f"Brier {r['brier']:.3f}, log loss {r['logloss']:.3f} "
              f"(always-home baseline Brier ~0.66, log loss ~1.09)")

    model = DixonColes().fit(matches, asof)
    print(f"Blend: {MARKET_WEIGHT[args.league]:.0%} bookmaker odds, {1 - MARKET_WEIGHT[args.league]:.0%} model")
    print(f"Home advantage x{math.exp(model.home_adv):.2f}, rho {model.rho:.3f}\n")
    for f in FIXTURES[args.league]:
        unknown = [t for t in (f["home"], f["away"]) if t not in model.idx]
        if unknown:
            mkt = devig(f["odds"])
            print(f"{f['home']} v {f['away']}  ({f['when']})  no data for {', '.join(unknown)}")
            print("   market only  1 {:.0%}  X {:.0%}  2 {:.0%}".format(*mkt))
            continue
        mat = model.score_matrix(f["home"], f["away"])
        mk = markets(mat)
        lam, mu = model.expected_goals(f["home"], f["away"])
        mod = np.array([mk["1"], mk["X"], mk["2"]])
        mkt = devig(f["odds"])
        wt = MARKET_WEIGHT[args.league]
        blend = wt * mkt + (1 - wt) * mod
        edge = blend * np.array(f["odds"]) - 1
        print(f"{f['home']} v {f['away']}  ({f['when']})  xG {lam:.2f}-{mu:.2f}")
        print("   model  1 {:.0%}  X {:.0%}  2 {:.0%}".format(*mod))
        print("   market 1 {:.0%}  X {:.0%}  2 {:.0%}".format(*mkt))
        print("   blend  1 {:.0%}  X {:.0%}  2 {:.0%}   EV/unit 1 {:+.2f} X {:+.2f} 2 {:+.2f}".format(*blend, *edge))
        print("   Over 2.5 {:.0%}  GG {:.0%}  likely scores {}".format(
            mk["O2.5"], mk["GG"], ", ".join(f"{s} ({p:.0%})" for s, p in mk["scores"])))


if __name__ == "__main__":
    main()
