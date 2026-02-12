"""Statistical comparison between simulation and measured thermocouple data.

Computes RMS error, peak temperature difference, R-squared correlation,
phase-by-phase metrics, and time offset detection via cross-correlation.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import numpy as np
import logging

logger = logging.getLogger(__name__)


@dataclass
class ComparisonMetrics:
    """Statistical comparison metrics between simulation and measured data."""
    rms_error: float = 0.0
    peak_temp_diff: float = 0.0
    r_squared: float = 0.0
    time_offset: float = 0.0
    max_abs_error: float = 0.0
    rating: str = 'unknown'
    phase_metrics: Dict[str, Dict[str, float]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            'rms_error': self.rms_error,
            'peak_temp_diff': self.peak_temp_diff,
            'r_squared': self.r_squared,
            'time_offset': self.time_offset,
            'max_abs_error': self.max_abs_error,
            'rating': self.rating,
            'phase_metrics': self.phase_metrics,
        }


class ComparisonService:
    """Computes comparison metrics between simulation and measured data."""

    GOOD_THRESHOLD = 15.0
    ACCEPTABLE_THRESHOLD = 30.0

    @staticmethod
    def compare(
        sim_times: np.ndarray,
        sim_temps: np.ndarray,
        meas_times: np.ndarray,
        meas_temps: np.ndarray,
    ) -> ComparisonMetrics:
        """Compare simulation and measured temperature histories.

        Interpolates both to a common time grid, computes metrics.

        Parameters
        ----------
        sim_times : np.ndarray
            Simulation time array (seconds)
        sim_temps : np.ndarray
            Simulation temperature array (degC)
        meas_times : np.ndarray
            Measured time array (seconds)
        meas_temps : np.ndarray
            Measured temperature array (degC)

        Returns
        -------
        ComparisonMetrics
        """
        if len(sim_times) < 2 or len(meas_times) < 2:
            return ComparisonMetrics()

        # Build common time grid (overlap region)
        t_start = max(sim_times[0], meas_times[0])
        t_end = min(sim_times[-1], meas_times[-1])
        if t_end <= t_start:
            return ComparisonMetrics()

        n_points = 500
        common_times = np.linspace(t_start, t_end, n_points)

        # Interpolate both to common grid
        sim_interp = np.interp(common_times, sim_times, sim_temps)
        meas_interp = np.interp(common_times, meas_times, meas_temps)

        # Compute metrics
        diff = sim_interp - meas_interp
        rms_error = float(np.sqrt(np.mean(diff**2)))
        peak_diff = float(np.max(sim_interp) - np.max(meas_interp))
        max_abs_error = float(np.max(np.abs(diff)))

        # R-squared
        ss_res = np.sum(diff**2)
        ss_tot = np.sum((meas_interp - np.mean(meas_interp))**2)
        r_squared = float(1 - ss_res / ss_tot) if ss_tot > 0 else 0.0

        # Time offset via cross-correlation
        time_offset = ComparisonService._detect_time_offset(
            common_times, sim_interp, meas_interp
        )

        # Rating
        if rms_error < ComparisonService.GOOD_THRESHOLD:
            rating = 'good'
        elif rms_error < ComparisonService.ACCEPTABLE_THRESHOLD:
            rating = 'acceptable'
        else:
            rating = 'poor'

        return ComparisonMetrics(
            rms_error=round(rms_error, 2),
            peak_temp_diff=round(peak_diff, 2),
            r_squared=round(max(r_squared, 0.0), 4),
            time_offset=round(time_offset, 2),
            max_abs_error=round(max_abs_error, 2),
            rating=rating,
        )

    @staticmethod
    def _detect_time_offset(times, sim_temps, meas_temps) -> float:
        """Detect best time alignment via cross-correlation."""
        dt = times[1] - times[0]
        sim_centered = sim_temps - np.mean(sim_temps)
        meas_centered = meas_temps - np.mean(meas_temps)
        cross_corr = np.correlate(sim_centered, meas_centered, mode='full')
        lags = np.arange(-len(sim_temps) + 1, len(sim_temps)) * dt
        best_lag_idx = np.argmax(cross_corr)
        return float(lags[best_lag_idx])

    @staticmethod
    def compare_simulation(simulation) -> Optional[ComparisonMetrics]:
        """Compare a simulation against its measured data.

        Uses the full cycle simulation result and the first available
        measured dataset channel for comparison.

        Parameters
        ----------
        simulation : Simulation
            Simulation model instance with measured_data relationship

        Returns
        -------
        ComparisonMetrics or None
        """
        try:
            # Get full cycle simulation result
            full_result = simulation.results.filter_by(
                result_type='full_cycle'
            ).first()
            if not full_result:
                return None

            sim_times = np.array(full_result.time_array)
            sim_temps = np.array(full_result.value_array)
            if len(sim_times) < 2:
                return None

            # Get measured data
            measured_list = simulation.measured_data.all()
            if not measured_list:
                return None

            # Use first measured dataset, first channel
            md = measured_list[0]
            channels = md.channels
            if not channels:
                return None

            first_channel = list(channels.keys())[0]
            meas_temps = np.array(channels[first_channel])
            meas_times = np.array(md.get_channel_times(first_channel))

            # Overall comparison
            overall = ComparisonService.compare(
                sim_times, sim_temps, meas_times, meas_temps
            )

            # Per-phase comparison
            step_phases = {
                'heating': 'heating',
                'quenching': 'quenching',
                'tempering': 'tempering',
            }
            for md_item in measured_list:
                step = md_item.process_step
                if step not in step_phases:
                    continue

                phase_ch = md_item.channels
                if not phase_ch:
                    continue

                ch_name = list(phase_ch.keys())[0]
                ph_temps = np.array(phase_ch[ch_name])
                ph_times = np.array(md_item.get_channel_times(ch_name))

                # Get matching simulation phase result
                phase_result = simulation.results.filter_by(
                    phase=step
                ).first()
                if not phase_result:
                    continue

                ph_sim_times = np.array(phase_result.time_array)
                ph_sim_temps = np.array(phase_result.value_array)
                if len(ph_sim_times) < 2:
                    continue

                ph_metrics = ComparisonService.compare(
                    ph_sim_times, ph_sim_temps, ph_times, ph_temps
                )
                overall.phase_metrics[step] = {
                    'rms': ph_metrics.rms_error,
                    'r_squared': ph_metrics.r_squared,
                    'rating': ph_metrics.rating,
                }

            return overall

        except Exception as e:
            logger.error(f"Comparison failed: {e}")
            return None
