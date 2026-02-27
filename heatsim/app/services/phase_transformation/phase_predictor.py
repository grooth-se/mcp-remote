"""Phase prediction orchestrator with three-tier fallback.

Tier 1: Digitized PhaseDiagram curves (if available in DB)
Tier 2: JMAK/Scheil CCT prediction (if TTTParameters exist for grade)
Tier 3: Empirical CCT predictor (cct_predictor.py, requires composition)

For phase fraction prediction:
Tier 2 uses Scheil additivity -> PhaseResult
Tier 3 falls back to the simplified PhaseTracker
"""
import logging
from typing import Dict, Optional, List

import numpy as np

from app.services.phase_tracker import PhaseResult

logger = logging.getLogger(__name__)


class PhasePredictor:
    """Orchestrates phase prediction with three-tier fallback.

    Parameters
    ----------
    steel_grade : SteelGrade
        Steel grade model with relationships
    """

    def __init__(self, steel_grade):
        self.grade = steel_grade
        self._ttt_params = None
        self._jmak_models = None
        self._martensite_model = None
        self._critical_temps = None
        self._loaded = False

    def _load(self):
        """Lazy-load TTT parameters and build JMAK models."""
        if self._loaded:
            return
        self._loaded = True

        from app.models.ttt_parameters import TTTParameters, JMAKParameters, MartensiteParameters
        from .jmak_model import JMAKModel, create_b_function
        from .martensite_model import KoistinenMarburgerModel

        self._ttt_params = TTTParameters.query.filter_by(
            steel_grade_id=self.grade.id
        ).first()

        if self._ttt_params is None:
            return

        # Build critical temps dict
        self._critical_temps = self._ttt_params.temps_dict

        # Build JMAK models for each phase
        self._jmak_models = {}
        for jmak in self._ttt_params.jmak_parameters.all():
            try:
                b_func = create_b_function(jmak.b_model_type, jmak.b_params_dict)
                temp_range = None
                if jmak.temp_range_min is not None and jmak.temp_range_max is not None:
                    temp_range = (jmak.temp_range_min, jmak.temp_range_max)
                model = JMAKModel(n=jmak.n_value, b_func=b_func, temp_range=temp_range)
                self._jmak_models[jmak.phase] = model
            except Exception as e:
                logger.warning("Failed to build JMAK model for %s: %s", jmak.phase, e)

        # Build martensite model
        mart_params = self._ttt_params.martensite_parameters
        if mart_params:
            self._martensite_model = KoistinenMarburgerModel(
                ms=mart_params.ms,
                mf=mart_params.mf,
                alpha=mart_params.alpha_m
            )
        elif self._ttt_params.ms:
            self._martensite_model = KoistinenMarburgerModel(
                ms=self._ttt_params.ms,
                mf=self._ttt_params.mf
            )

    @property
    def is_available(self) -> bool:
        """Check if JMAK-based prediction is available."""
        self._load()
        return self._jmak_models is not None and len(self._jmak_models) > 0

    @property
    def tier(self) -> str:
        """Return which prediction tier is active."""
        # Check Tier 1: digitized diagram
        diagram = self.grade.phase_diagrams.filter_by(diagram_type='CCT').first()
        if diagram and diagram.curves:
            return 'digitized'

        # Check Tier 2: JMAK
        if self.is_available:
            return 'jmak'

        # Check Tier 3: empirical
        if self.grade.composition:
            return 'empirical'

        return 'none'

    def predict_phases_scheil(
        self,
        times: np.ndarray,
        temperatures: np.ndarray,
        t8_5: Optional[float] = None
    ) -> PhaseResult:
        """Predict phases using Scheil additivity (Tier 2).

        Falls back to empirical PhaseTracker if JMAK not available.

        Parameters
        ----------
        times : np.ndarray
            Time array (seconds)
        temperatures : np.ndarray
            Temperature array (deg C)
        t8_5 : float, optional
            Cooling time 800-500 deg C

        Returns
        -------
        PhaseResult
            Phase fractions (same format as PhaseTracker)
        """
        self._load()

        if self._jmak_models and len(self._jmak_models) > 0:
            try:
                return self._predict_scheil(times, temperatures)
            except Exception as e:
                logger.warning("Scheil prediction failed, falling back: %s", e)

        # Fallback to simplified PhaseTracker
        from app.services.phase_tracker import PhaseTracker
        diagram = self.grade.phase_diagrams.first()
        tracker = PhaseTracker(diagram)
        return tracker.predict_phases(times, temperatures, t8_5)

    def _predict_scheil(self, times: np.ndarray, temperatures: np.ndarray) -> PhaseResult:
        """Internal Scheil prediction."""
        from .scheil_additivity import calculate_cct_transformation

        result = calculate_cct_transformation(
            times, temperatures,
            self._jmak_models,
            self._martensite_model,
            self._critical_temps
        )

        # Convert to PhaseResult
        return PhaseResult(
            martensite=result.final_fractions.get('martensite', 0.0),
            bainite=result.final_fractions.get('bainite', 0.0),
            ferrite=result.final_fractions.get('ferrite', 0.0),
            pearlite=result.final_fractions.get('pearlite', 0.0),
            retained_austenite=result.final_fractions.get('retained_austenite', 0.0),
        ).normalize()

    def get_cct_curves(self) -> Optional[Dict]:
        """Get CCT curves using three-tier fallback.

        Returns
        -------
        dict or None
            {phase: {'start': [[t,T],...], 'finish': [[t,T],...]}}
        """
        # Tier 1: digitized curves from DB
        diagram = self.grade.phase_diagrams.filter_by(diagram_type='CCT').first()
        if diagram and diagram.curves:
            curves = diagram.curves_dict
            if curves:
                logger.debug("Using digitized CCT curves for %s", self.grade.designation)
                return curves

        # Tier 2: JMAK-generated CCT
        self._load()
        if self._jmak_models and len(self._jmak_models) > 0:
            try:
                from .cct_generator import generate_cct_from_ttt
                austenitizing = 900.0
                if self._ttt_params and self._ttt_params.austenitizing_temperature:
                    austenitizing = self._ttt_params.austenitizing_temperature

                curves = generate_cct_from_ttt(
                    self._jmak_models,
                    self._martensite_model,
                    self._critical_temps,
                    austenitizing_temp=austenitizing
                )
                if curves:
                    logger.debug("Using JMAK CCT curves for %s", self.grade.designation)
                    return curves
            except Exception as e:
                logger.warning("JMAK CCT generation failed: %s", e)

        # Tier 3: empirical predictor
        if self.grade.composition:
            try:
                from app.services.cct_predictor import predict_cct_curves
                comp = self.grade.composition.to_dict()
                trans_temps = None
                if diagram:
                    trans_temps = diagram.temps_dict
                curves = predict_cct_curves(comp, trans_temps)
                if curves:
                    logger.debug("Using empirical CCT curves for %s", self.grade.designation)
                    return curves
            except Exception as e:
                logger.warning("Empirical CCT prediction failed: %s", e)

        return None

    def get_ttt_curves(self) -> Optional[Dict]:
        """Get TTT curves (JMAK only, or digitized).

        Returns
        -------
        dict or None
            {phase: {'start': [[t,T],...], 'finish': [[t,T],...]}}
        """
        # Tier 1: digitized TTT from DB
        diagram = self.grade.phase_diagrams.filter_by(diagram_type='TTT').first()
        if diagram and diagram.curves:
            curves = diagram.curves_dict
            if curves:
                return curves

        # Tier 2: generated from JMAK
        self._load()
        if self._jmak_models and len(self._jmak_models) > 0:
            try:
                from .ttt_generator import generate_ttt_for_plotting
                return generate_ttt_for_plotting(
                    self._jmak_models, self._critical_temps
                )
            except Exception as e:
                logger.warning("TTT generation failed: %s", e)

        return None

    def get_transformation_temps(self) -> Dict[str, Optional[float]]:
        """Get transformation temperatures from best available source."""
        self._load()

        # From TTT parameters
        if self._ttt_params:
            return self._ttt_params.temps_dict

        # From phase diagram
        diagram = self.grade.phase_diagrams.first()
        if diagram:
            return diagram.temps_dict

        # From composition (empirical)
        if self.grade.composition:
            from .critical_temperatures import calculate_critical_temperatures
            return calculate_critical_temperatures(self.grade.composition.to_dict())

        return {}
