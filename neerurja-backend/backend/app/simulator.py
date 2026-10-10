"""Physical model of the pump + tank + solar + grid system.

Pure standard-library code: no FastAPI, Pydantic or AWS imports, so it can be
tested on its own. The optimizer plans with the SAME helper functions
(`power_flows`, `slot_money`, `tank_step`) that the evaluator uses, so planning
and evaluation can never disagree about the physics.

Model, per interval t (dt = interval hours):
  pump_kw      = pump power if ON else 0
  load_kw      = other building load + pump_kw
  solar_used   = min(solar, load)
  grid_import  = load - solar_used            (>= 0)
  surplus      = solar - solar_used           (>= 0)
      zero_export        -> surplus is curtailed (no payment)
      compensated_export -> surplus is exported and paid at the export tariff
  tank_net     = level + delivered - demand,  delivered = flow_lph * dt if ON
      net > maximum_level -> excess is SPILLED, level = maximum_level
      net < 0             -> shortfall is UNMET demand, level = 0
"""

from dataclasses import dataclass

EPS = 1e-9


@dataclass(frozen=True)
class SimInputs:
    """Everything needed to simulate or plan one day. Profiles are tuples (immutable)."""

    interval_minutes: int
    solar_kw: tuple[float, ...]
    water_demand_litres: tuple[float, ...]  # litres per interval
    other_load_kw: tuple[float, ...]
    import_tariff: tuple[float, ...]  # INR/kWh per interval
    pump_power_kw: float
    pump_flow_lph: float
    min_run_slots: int
    max_starts: int
    tank_min: float
    tank_max: float
    tank_initial: float
    sanctioned_load_kw: float
    export_policy: str
    export_tariff: float

    @property
    def n_slots(self) -> int:
        return len(self.solar_kw)

    @property
    def dt_hours(self) -> float:
        return self.interval_minutes / 60.0

    @property
    def flow_per_slot(self) -> float:
        return self.pump_flow_lph * self.dt_hours

    def __post_init__(self):
        n = len(self.solar_kw)
        for name in ("water_demand_litres", "other_load_kw", "import_tariff"):
            if len(getattr(self, name)) != n:
                raise ValueError(f"{name} has {len(getattr(self, name))} entries, expected {n}")


@dataclass
class SimResult:
    pump_on: list[int]
    level: list[float]  # end-of-interval tank level
    grid_import_kw: list[float]
    solar_used_kw: list[float]
    curtailed_kw: list[float]
    exported_kw: list[float]
    pump_kw: list[float]
    load_kw: list[float]
    spilled_litres: list[float]
    unmet_litres: list[float]
    import_cost_inr: float
    export_revenue_inr: float


# ----------------------------------------------------------------- shared physics
def power_flows(solar_kw: float, other_kw: float, pump_on: int, pump_power_kw: float):
    """Return (pump_kw, load_kw, solar_used_kw, grid_import_kw, surplus_kw)."""
    pump_kw = pump_power_kw if pump_on else 0.0
    load = other_kw + pump_kw
    used = min(solar_kw, load)
    return pump_kw, load, used, load - used, solar_kw - used


def slot_money(grid_kw: float, surplus_kw: float, tariff: float, export_policy: str,
               export_tariff: float, dt_hours: float):
    """Return (import_cost, export_revenue, exported_kwh, curtailed_kwh) for one interval."""
    import_cost = grid_kw * dt_hours * tariff
    if export_policy == "compensated_export":
        exported = surplus_kw * dt_hours
        return import_cost, exported * export_tariff, exported, 0.0
    return import_cost, 0.0, 0.0, surplus_kw * dt_hours


def tank_step(level: float, delivered: float, demand: float, tank_max: float):
    """Return (new_level, spilled, unmet)."""
    net = level + delivered - demand
    if net > tank_max:
        return tank_max, net - tank_max, 0.0
    if net < 0.0:
        return 0.0, 0.0, -net
    return net, 0.0, 0.0


# ------------------------------------------------------------------- simulation
def simulate(schedule, inp: SimInputs) -> SimResult:
    """Evaluate a 0/1 pump schedule against the profiles in `inp`."""
    n = inp.n_slots
    if len(schedule) != n:
        raise ValueError(f"schedule has {len(schedule)} entries, expected {n}")
    if any(s not in (0, 1) for s in schedule):
        raise ValueError("schedule must contain only 0/1")

    dt = inp.dt_hours
    level = inp.tank_initial
    r = SimResult([int(s) for s in schedule], [], [], [], [], [], [], [], [], [], 0.0, 0.0)
    for t in range(n):
        on = r.pump_on[t]
        pump_kw, load, used, grid, surplus = power_flows(
            inp.solar_kw[t], inp.other_load_kw[t], on, inp.pump_power_kw
        )
        imp_cost, revenue, exported_kwh, curtailed_kwh = slot_money(
            grid, surplus, inp.import_tariff[t], inp.export_policy, inp.export_tariff, dt
        )
        delivered = inp.flow_per_slot if on else 0.0
        level, spilled, unmet = tank_step(level, delivered, inp.water_demand_litres[t], inp.tank_max)

        r.level.append(level)
        r.grid_import_kw.append(grid)
        r.solar_used_kw.append(used)
        r.curtailed_kw.append(curtailed_kwh / dt)
        r.exported_kw.append(exported_kwh / dt)
        r.pump_kw.append(pump_kw)
        r.load_kw.append(load)
        r.spilled_litres.append(spilled)
        r.unmet_litres.append(unmet)
        r.import_cost_inr += imp_cost
        r.export_revenue_inr += revenue
    return r


# -------------------------------------------------------------- schedule helpers
def runs(schedule):
    """List of (start_index, length) for each consecutive ON run."""
    out, start = [], None
    for i, s in enumerate(schedule):
        if s and start is None:
            start = i
        elif not s and start is not None:
            out.append((start, i - start))
            start = None
    if start is not None:
        out.append((start, len(schedule) - start))
    return out


def count_starts(schedule) -> int:
    """OFF->ON transitions; the pump is assumed OFF before the first interval."""
    return len(runs(schedule))


def count_min_run_violations(schedule, min_run_slots: int) -> int:
    """Runs shorter than the minimum that END inside the day.

    A run still ON at the last interval is not counted: it continues into the next day.
    """
    n = len(schedule)
    return sum(1 for start, length in runs(schedule) if length < min_run_slots and start + length < n)
