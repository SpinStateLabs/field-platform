"""Per-(route, dimension) hygiene drift tracking (ADR 10 §2; v1.2 D2b) —
trend alerts, never points.

Judged scores aggregate into count-based windows per SERIES, a series being
``(route, dimension)``: route = FORCE preset, dimension = one judged quality
(the gateway feeds ``overall`` and ``sycophancy``). Each series keeps its own
baseline: the first ``baseline_windows`` completed windows fix it; an alert
fires exactly when TWO consecutive completed windows fall outside
``baseline ± band`` — single-window noise never alarms (alarm fatigue kills a
dashboard's authority). After an alert the series re-arms only once a window
lands back inside the band. So sycophancy can drift while overall holds, and
the alert names the dimension that moved.

A judge-model or rubric-version change resets EVERY series of that route
(ADR 10 §3: baselines are recomputed on any judge change — comparing scores
across judges is meaningless, and one judgment feeds all of a route's series).

State is rebuilt at startup by replaying the persisted ``drift_scores`` rows
in order (``force_gateway.store``) — the logic is deterministic, so the replay
reproduces baselines, windows and alert state exactly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: the dimensions the gateway feeds from each hygiene judgment, in order
DIMENSIONS = ("overall", "sycophancy")


@dataclass
class DriftAlert:
    route: str
    dimension: str
    baseline_mean: float
    band: float
    window_means: tuple[float, float]
    model: str
    rubric_version: str


@dataclass
class _SeriesState:
    scores: list[float] = field(default_factory=list)  # current window
    window_means: list[float] = field(default_factory=list)
    baseline_mean: float | None = None
    consecutive_out: int = 0
    alert_active: bool = False
    alerts_fired: int = 0
    model: str | None = None
    rubric_version: str | None = None


class DriftTracker:
    def __init__(self, window_size: int = 5, band: float = 0.15,
                 baseline_windows: int = 2):
        self.window_size = window_size
        self.band = band
        self.baseline_windows = baseline_windows
        self._series: dict[tuple[str, str], _SeriesState] = {}

    def record(self, route: str, dimension: str, score: float, model: str,
               rubric_version: str) -> DriftAlert | None:
        key = (route, dimension)
        st = self._series.get(key)
        if st is None or (st.model, st.rubric_version) != (model, rubric_version):
            # Judge changed (or first score): scores are no longer comparable
            # across the whole route — start every series of it over.
            for other in [k for k in self._series if k[0] == route]:
                other_st = self._series[other]
                if (other_st.model, other_st.rubric_version) != (model, rubric_version):
                    self._series[other] = _SeriesState(
                        model=model, rubric_version=rubric_version)
            st = self._series.setdefault(
                key, _SeriesState(model=model, rubric_version=rubric_version))

        st.scores.append(score)
        if len(st.scores) < self.window_size:
            return None

        mean = sum(st.scores) / len(st.scores)
        st.scores = []
        st.window_means.append(mean)

        if st.baseline_mean is None:
            if len(st.window_means) >= self.baseline_windows:
                baseline = st.window_means[: self.baseline_windows]
                st.baseline_mean = sum(baseline) / len(baseline)
            return None

        out_of_band = abs(mean - st.baseline_mean) > self.band
        if not out_of_band:
            st.consecutive_out = 0
            st.alert_active = False  # recovery re-arms the series
            return None

        st.consecutive_out += 1
        if st.consecutive_out >= 2 and not st.alert_active:
            st.alert_active = True
            st.alerts_fired += 1
            return DriftAlert(
                route=route, dimension=dimension,
                baseline_mean=round(st.baseline_mean, 4), band=self.band,
                window_means=(round(st.window_means[-2], 4),
                              round(st.window_means[-1], 4)),
                model=model, rubric_version=rubric_version,
            )
        return None

    def status(self) -> dict[str, dict[str, dict]]:
        """``{route: {dimension: state}}``."""
        out: dict[str, dict[str, dict]] = {}
        for (route, dimension), st in self._series.items():
            out.setdefault(route, {})[dimension] = {
                "baseline_mean": (round(st.baseline_mean, 4)
                                  if st.baseline_mean is not None else None),
                "band": self.band,
                "window_size": self.window_size,
                "completed_windows": [round(m, 4) for m in st.window_means],
                "scores_in_current_window": len(st.scores),
                "consecutive_out_of_band": st.consecutive_out,
                "alert_active": st.alert_active,
                "alerts_fired": st.alerts_fired,
                "model": st.model,
                "rubric_version": st.rubric_version,
            }
        return out

    def active_alerts(self) -> list[dict[str, str]]:
        return [{"route": route, "dimension": dimension}
                for (route, dimension), st in self._series.items()
                if st.alert_active]
