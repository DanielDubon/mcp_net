import asyncio, json
from dataclasses import dataclass
from typing import Dict, List, Literal

from mcp.server.fastmcp import FastMCP


mcp = FastMCP("f1-strategy-mcp")

# ----- Datos DEMO -----
@dataclass
class Race:
    race_id: str
    season: int
    name: str
    laps: int
    pit_loss_s: float
    compounds: List[Literal["SOFT", "MEDIUM", "HARD"]]

RACES: Dict[str, Race] = {
    "demo_mexico_2024": Race("demo_mexico_2024", 2024, "Demo Mexico City GP", 57, 20.0, ["SOFT", "MEDIUM", "HARD"]),
    "demo_monza_2024": Race("demo_monza_2024", 2024, "Demo Italian GP (Monza)", 53, 18.5, ["SOFT", "MEDIUM", "HARD"]),
}

# ----- Utilidades ----
def stint_time_s(base_laptime_s: float, deg_per_lap_s: float, stint_laps: int) -> float:
    L = stint_laps
    return L * base_laptime_s + deg_per_lap_s * (L * (L - 1) / 2.0)

def enumerate_splits(total_laps: int, min_stint: int, max_stint: int, max_stops: int) -> List[List[int]]:
    plans: List[List[int]] = []
    def rec(rem: int, cur: List[int], left: int):
        if left == 1:
            if min_stint <= rem <= max_stint: plans.append(cur + [rem])
            return
        for x in range(min_stint, max_stint + 1):
            if x > rem: break
            if rem - x < (left - 1) * min_stint: continue
            if rem - x > (left - 1) * max_stint: continue
            rec(rem - x, cur + [x], left - 1)
    for k in range(1, max_stops + 2):
        if k * min_stint <= total_laps <= k * max_stint:
            rec(total_laps, [], k)
    return plans

def all_compound_sequences(comps: List[str], k: int) -> List[List[str]]:
    if k == 0: return [[]]
    res: List[List[str]] = []
    def rec(cur: List[str]):
        if len(cur) == k: res.append(cur[:]); return
        for c in comps:
            cur.append(c); rec(cur); cur.pop()
    rec([])
    return res

def solve_strategy(
    race: Race,
    base_laptime_s: float,
    deg_profile: Dict[str, float],
    min_stint_laps: int,
    max_stint_laps: int,
    max_stops: int = 2,
    enforce_two_compounds: bool = True
) -> Dict:
    best = None
    splits = enumerate_splits(race.laps, min_stint_laps, max_stint_laps, max_stops)
    cache: Dict[int, List[List[str]]] = {}
    for plan in splits:
        k = len(plan)
        if k not in cache:
            cache[k] = all_compound_sequences(race.compounds, k)
        for seq in cache[k]:
            # Regla de la FIA: si hay ≥2 stints, deben usarse ≥2 compuestos distintos (carrera seca)
            if enforce_two_compounds and k >= 2 and len(set(seq)) < 2:
                continue

            total = 0.0
            breakdown: List[float] = []
            for laps, comp in zip(plan, seq):
                stint = stint_time_s(base_laptime_s, deg_profile.get(comp, 0.0), laps)
                breakdown.append(stint)
                total += stint
            total += (k - 1) * race.pit_loss_s

            if (best is None) or (total < best[0]):
                stops, acc = [], 0
                for i in range(k - 1):
                    acc += plan[i]
                    stops.append(acc)
                best = (total, plan, seq, stops, breakdown)

    if best is None:
        return {"ok": False, "error": "No feasible plan with given constraints."}

    total, plan, seq, stops, bd = best
    return {
        "ok": True,
        "race_id": race.race_id,
        "strategy": [f"{c}: {L}" for c, L in zip(seq, plan)],
        "stop_laps": stops,
        "predicted_total_s": round(total, 3),
        "stint_breakdown_s": [round(x, 3) for x in bd],
        "notes": f"{len(plan)-1} stop(s); pit_loss={race.pit_loss_s}s; base={base_laptime_s}s; deg={deg_profile}"
    }


# --- Herramientas MCP -----
@mcp.tool()
async def get_calendar(season: int) -> str:
    cal = [{"race_id": r.race_id, "name": r.name, "laps": r.laps}
           for r in RACES.values() if r.season == season]
    return json.dumps({"season": season, "races": cal}, ensure_ascii=False, indent=2)

@mcp.tool()
async def get_race(race_id: str) -> str:
    r = RACES.get(race_id)
    if not r:
        return json.dumps({"ok": False, "error": "race_id not found"}, ensure_ascii=False)
    return json.dumps({"ok": True, "race_id": r.race_id, "name": r.name, "season": r.season,
                       "laps": r.laps, "pit_loss_s": r.pit_loss_s, "compounds": r.compounds},
                      ensure_ascii=False, indent=2)

@mcp.tool()
async def recommend_strategy(race_id: str, base_laptime_s: float,
                             deg_soft_s: float, deg_medium_s: float, deg_hard_s: float,
                             min_stint_laps: int, max_stint_laps: int, max_stops: int = 2) -> str:
    r = RACES.get(race_id)
    if not r:
        return json.dumps({"ok": False, "error": "race_id not found"}, ensure_ascii=False)
    deg = {"SOFT": deg_soft_s, "MEDIUM": deg_medium_s, "HARD": deg_hard_s}
    res = solve_strategy(r, base_laptime_s, deg, min_stint_laps, max_stint_laps, max_stops, enforce_two_compounds=True)
    return json.dumps(res, ensure_ascii=False, indent=2)

async def amain():
    async with stdio_server() as (reader, writer):
        await mcp.run("stdio", reader, writer) 

if __name__ == "__main__":
    mcp.run("stdio")
