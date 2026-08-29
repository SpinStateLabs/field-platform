"""Per-route hygiene drift tracking (ADR 10 §2) — trend alerts, never points.

Judged overall scores aggregate into count-based windows per route (= FORCE
preset). The first ``baseline_windows`` completed windows fix the route's
baseline mean; an alert fires exactly when TWO consecutive completed windows
fall outside ``baseline ± band`` — single-window noise never alarms (alarm
fatigue kills a dashboard's authority). After an alert the route re-arms only
once a window lands back inside the band.

A judge-model or rubric-version change resets the route's baseline (ADR 10
§3: baselines are recomputed on any judge change — comparing scores across
judges is meaningless).

State is in-memory and session-scoped — README LIMITS; the telemetry
persistence backlog item will feed this same logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DriftAlert:
    route: str
    baseline_mean: float
    band: float
    window_means: tuple[float, float]
    model: str
    rubric_version: str


@dataclass
class _RouteState:
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
        self._routes: dict[str, _RouteState] = {}

    def record(self, route: str, overall: float, model: str,
               rubric_version: str) -> DriftAlert | None:
        st = self._routes.setdefault(route, _RouteState())
        if (st.model, st.rubric_version) != (model, rubric_version):
            # Judge changed: scores are no longer comparable — start over.
            self._routes[route] = st = _RouteState()
            st.model, st.rubric_version = model, rubric_version

        st.scores.append(overall)
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
            st.alert_active = False  # recovery re-arms the route
            return None

        st.consecutive_out += 1
        if st.consecutive_out >= 2 and not st.alert_active:
            st.alert_active = True
            st.alerts_fired += 1
            return DriftAlert(
                route=route, baseline_mean=round(st.baseline_mean, 4),
                band=self.band,
                window_means=(round(st.window_means[-2], 4),
                              round(st.window_means[-1], 4)),
                model=model, rubric_version=rubric_version,
            )
        return None

    def status(self) -> dict[str, dict]:
        out = {}
        for route, st in self._routes.items():
            out[route] = {
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
