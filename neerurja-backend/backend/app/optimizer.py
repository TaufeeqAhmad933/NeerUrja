"""Forecast-aware pump scheduler: dynamic programming over (tank level, pump run state, starts).

IMPORTANT: `optimize_schedule` receives ONE `SimInputs`. The caller must build it
from the FORECAST solar and FORECAST water-demand profiles. The function has no
access to actual profiles, so it cannot use future knowledge.

Algorithm (forward DP over intervals t = 0..n-1)
------------------------------------------------
State  = (level bucket, run state r, starts used s)
  r = 0        pump OFF
  r = 1..R-1   pump ON, minimum run not yet satisfied  (R = min run in intervals)
  r = R        pump ON and the minimum run is satisfied ("free to stop")
Action = pump OFF or ON in interval t.
  * OFF is allowed only if r == 0 or r == R   (minimum runtime)
  * OFF->ON consumes one start; s must stay <= max_starts_per_day
  * ON is not allowed if forecast grid import would exceed the sanctioned load
  * the tank level after the interval, computed with the forecast demand, must
    stay within [floor, maximum_level]  (no overflow, no shortage, a safety reserve)
  * at the end of the day r must be 0 or R (no run cut short) and the level must
    be >= the terminal target (default: the initial level, so the plan cannot
    "win" by draining the tank)
Objective (lexicographic): minimise forecast electricity cost (import cost minus
export revenue), then number of starts, then pump runtime, then prefer pumping in
intervals with more forecast solar headroom (a hedge against forecast error that
never overrides cost).

Discretisation and its limits
-----------------------------
Levels are bucketed with step `level_step_litres` ONLY to merge states. Each
state keeps the exact continuous level of its best path, so every schedule
returned is exactly feasible under the forecast (no rounding drift). When two
paths land in the same bucket with the same (r, s), only the cheaper one is
kept. That pruning is the sole approximation:
  * with a bucket step small enough that distinct reachable levels never share a
    bucket, the result is exactly optimal (verified against brute force in
    tests/test_optimizer.py);
  * with the coarser default step the schedule is feasible and near-optimal, but
    optimality is not guaranteed.
Feasibility is guaranteed only under the FORECAST. Evaluation against actual
conditions can still show shortages, spills or limit violations, and those are
reported by the evaluator.
"""

import math
from dataclasses import dataclass, field

from .simulator import EPS, SimInputs, power_flows, slot_money


class InfeasibleScheduleError(Exception):
    """No pump schedule satisfies all constraints under the forecast."""

    def __init__(self, message: str, details: list[str] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or []


@dataclass(frozen=True)
class OptimizerConfig:
    level_step_litres: float | None = None  # None -> usable range / 80, at least 10 L
    reserve_fraction: float = 0.05  # safety reserve above minimum, as fraction of usable range
    terminal_at_least_initial: bool = True


@dataclass
class OptimizerResult:
    schedule: list[int]
    planned_cost_inr: float  # modelled cost UNDER THE FORECAST (not the evaluated cost)
    level_step_litres: float
    reserve_litres: float
    terminal_level_litres: float
    notes: list[str] = field(default_factory=list)  # relaxations applied (surfaced as warnings)


def _plan(inp: SimInputs, floor: float, terminal: float, step: float):
    """Run the DP once. Returns (schedule, cost) or None when infeasible."""
    n = inp.n_slots
    dt = inp.dt_hours
    flow = inp.flow_per_slot
    R = max(1, inp.min_run_slots)
    S = min(inp.max_starts, n)

    cost = []  # cost[t][on]
    allowed_on = []
    risk_on = []  # tie-break only: lower = more forecast solar headroom beyond the pump's own draw
    for t in range(n):
        row = []
        for on in (0, 1):
            _, _, _, grid, surplus = power_flows(inp.solar_kw[t], inp.other_load_kw[t], on, inp.pump_power_kw)
            imp, rev, _, _ = slot_money(grid, surplus, inp.import_tariff[t], inp.export_policy, inp.export_tariff, dt)
            row.append(imp - rev)
            if on:
                allowed_on.append(grid <= inp.sanctioned_load_kw + EPS)
                headroom = inp.solar_kw[t] - inp.other_load_kw[t] - inp.pump_power_kw
                risk_on.append(-min(headroom, 2.0 * inp.pump_power_kw))
        cost.append(row)

    def bucket(level: float) -> int:
        return int(round(level / step))

    # node = (cost, starts, runtime_slots, risk, exact_level, prev_key, action)
    layers = [{(bucket(inp.tank_initial), 0, 0): (0.0, 0, 0, 0.0, inp.tank_initial, None, 0)}]

    def offer(nxt, key, val, level, prev, action):
        old = nxt.get(key)
        if old is None or val < old[:4] or (val == old[:4] and level > old[4]):
            nxt[key] = (*val, level, prev, action)

    for t in range(n):
        nxt = {}
        d = inp.water_demand_litres[t]
        for key, node in layers[t].items():
            _, r, s = key
            c0, st0, rt0, rk0, level = node[0], node[1], node[2], node[3], node[4]

            if r == 0 or r >= R:  # OFF
                nl = level - d
                if nl >= floor - EPS:
                    offer(nxt, (bucket(nl), 0, s), (round(c0 + cost[t][0], 9), st0, rt0, rk0), nl, key, 0)

            if allowed_on[t]:  # ON
                if r == 0:
                    if s >= S:
                        continue
                    r2, s2, started = 1, s + 1, 1
                else:
                    r2, s2, started = min(r + 1, R), s, 0
                nl = level + flow - d
                if floor - EPS <= nl <= inp.tank_max + EPS:
                    offer(nxt, (bucket(nl), r2, s2),
                          (round(c0 + cost[t][1], 9), st0 + started, rt0 + 1,
                           round(rk0 + risk_on[t], 6)), nl, key, 1)
        if not nxt:
            return None
        layers.append(nxt)

    best_key, best = None, None
    for key, node in layers[n].items():
        _, r, _ = key
        if (r == 0 or r >= R) and node[4] >= terminal - EPS:
            rank = (node[0], node[1], node[2], node[3], -node[4])
            if best is None or rank < best:
                best_key, best = key, rank
    if best_key is None:
        return None

    schedule = [0] * n
    key = best_key
    for t in range(n, 0, -1):
        node = layers[t][key]
        schedule[t - 1] = node[6]
        key = node[5]
    return schedule, layers[n][best_key][0]


def optimize_schedule(inp: SimInputs, config: OptimizerConfig | None = None) -> OptimizerResult:
    """Return the cheapest feasible schedule under the forecast, or raise InfeasibleScheduleError."""
    cfg = config or OptimizerConfig()
    usable = max(inp.tank_max - inp.tank_min, 0.0)
    step = cfg.level_step_litres or max(10.0, usable / 80.0)
    if not (math.isfinite(step) and step > 0):
        raise ValueError("level_step_litres must be a positive finite number")
    reserve = cfg.reserve_fraction * usable

    # Ladder of progressively relaxed requirements; the first feasible one wins and
    # every relaxation is reported to the caller.
    attempts = []
    for res in ([reserve, 0.0] if reserve > 0 else [0.0]):
        for term_initial in ([True, False] if cfg.terminal_at_least_initial else [False]):
            attempts.append((res, term_initial))

    for res, term_initial in attempts:
        floor = inp.tank_min + res
        terminal = max(inp.tank_initial, floor) if term_initial else floor
        out = _plan(inp, floor, terminal, step)
        if out is None:
            continue
        schedule, planned_cost = out
        notes = []
        if res < reserve:
            notes.append(
                f"Optimizer could not keep the {reserve:.0f} L planning reserve above the minimum tank "
                "level; it was relaxed to 0 L, so the plan has no safety margin against forecast error."
            )
        if cfg.terminal_at_least_initial and not term_initial:
            notes.append(
                "Optimizer could not end the day with at least the initial tank level; the end-of-day "
                "level target was relaxed to the minimum level (+ reserve)."
            )
        return OptimizerResult(schedule, planned_cost, step, res, terminal, notes)

    raise InfeasibleScheduleError(
        "No pump schedule satisfies the tank limits, pump limits and electrical limit under the "
        "forecast demand.",
        [
            f"Pump delivers {inp.flow_per_slot:.0f} L per {inp.interval_minutes}-minute interval "
            f"({inp.pump_flow_lph:.0f} L/h).",
            f"Allowed starts per day: {inp.max_starts}; minimum run: {inp.min_run_slots} intervals.",
            f"Tank bounds: {inp.tank_min:.0f}-{inp.tank_max:.0f} L, initial {inp.tank_initial:.0f} L.",
            f"Sanctioned load: {inp.sanctioned_load_kw:.1f} kW (pump {inp.pump_power_kw:.1f} kW).",
            "Typical causes: pump too small for the forecast demand, tank bounds too tight, "
            "too few allowed starts, or the pump cannot run within the sanctioned load.",
        ],
    )
