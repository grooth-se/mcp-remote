"""Preheat temperature calculator for welding.

Implements:
- Carbon Equivalent (CE_IIW, Pcm, CEN) calculations
- EN 1011-2 preheat temperature estimation
- Hydrogen cracking risk assessment

References:
- EN 1011-2:2001 "Welding — Recommendation for welding of metallic materials —
  Part 2: Arc welding of ferritic steels"
- Yurioka N., "Weldability of steels by carbon equivalent" (CEN formula)
- AWS D1.1 preheat requirements
"""
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
import math


# Hydrogen scale definitions (ml H2/100g deposited metal)
HYDROGEN_LEVELS = {
    'A': 5.0,    # Very low hydrogen
    'B': 10.0,   # Low hydrogen
    'C': 15.0,   # Medium hydrogen
    'D': 20.0,   # High hydrogen
}


@dataclass
class PreheatResult:
    """Result of preheat calculation.

    Attributes
    ----------
    ce_iiw : float
        Carbon equivalent (IIW formula)
    ce_pcm : float
        Carbon equivalent (Pcm formula)
    ce_cen : float
        Carbon equivalent (CEN formula)
    preheat_en1011_2 : float
        Recommended preheat temperature per EN 1011-2 (°C)
    preheat_method : str
        Method used for preheat recommendation
    hydrogen_level : str
        Hydrogen level designation (A/B/C/D)
    plate_thickness_mm : float
        Combined plate thickness (mm)
    heat_input_kj_mm : float
        Heat input (kJ/mm)
    cracking_risk : str
        Risk level: 'low', 'medium', 'high'
    cracking_notes : list
        Explanatory notes about cracking risk factors
    """
    ce_iiw: float = 0.0
    ce_pcm: float = 0.0
    ce_cen: float = 0.0
    preheat_en1011_2: float = 20.0
    preheat_method: str = ''
    hydrogen_level: str = 'B'
    plate_thickness_mm: float = 20.0
    heat_input_kj_mm: float = 1.5
    cracking_risk: str = 'low'
    cracking_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to serializable dictionary."""
        return {
            'ce_iiw': round(self.ce_iiw, 4),
            'ce_pcm': round(self.ce_pcm, 4),
            'ce_cen': round(self.ce_cen, 4),
            'preheat_en1011_2': round(self.preheat_en1011_2, 0),
            'preheat_method': self.preheat_method,
            'hydrogen_level': self.hydrogen_level,
            'plate_thickness_mm': self.plate_thickness_mm,
            'heat_input_kj_mm': round(self.heat_input_kj_mm, 2),
            'cracking_risk': self.cracking_risk,
            'cracking_notes': self.cracking_notes,
        }


class PreheatCalculator:
    """Calculates preheat requirements for welding.

    Uses carbon equivalent formulas and EN 1011-2 methods to
    determine minimum preheat temperature and assess cracking risk.
    """

    def __init__(self, composition):
        """Initialize with steel composition.

        Parameters
        ----------
        composition : SteelComposition
            Steel composition model instance
        """
        self.comp = composition
        self.C = composition.carbon or 0.0
        self.Si = composition.silicon or 0.0
        self.Mn = composition.manganese or 0.0
        self.Cu = composition.copper or 0.0
        self.Cr = composition.chromium or 0.0
        self.Ni = composition.nickel or 0.0
        self.Mo = composition.molybdenum or 0.0
        self.V = composition.vanadium or 0.0
        self.Nb = composition.niobium or 0.0
        self.B = composition.boron or 0.0

    @property
    def ce_iiw(self) -> float:
        """CE(IIW) = C + Mn/6 + (Cr+Mo+V)/5 + (Ni+Cu)/15."""
        return self.comp.carbon_equivalent_iiw

    @property
    def ce_pcm(self) -> float:
        """Pcm = C + Si/30 + (Mn+Cu+Cr)/20 + Ni/60 + Mo/15 + V/10 + 5B."""
        return self.comp.carbon_equivalent_pcm

    def calculate_ce_cen(self) -> float:
        """Calculate CEN carbon equivalent (Yurioka formula).

        CEN = C + A(C) × [Si/24 + Mn/6 + Cu/15 + Ni/20 + (Cr+Mo+Nb+V)/5 + 5B]
        A(C) = 0.75 + 0.25 × tanh(20 × (C - 0.12))

        Returns
        -------
        float
            CEN carbon equivalent
        """
        A_C = 0.75 + 0.25 * math.tanh(20 * (self.C - 0.12))

        alloy_term = (self.Si / 24 + self.Mn / 6 + self.Cu / 15 +
                      self.Ni / 20 + (self.Cr + self.Mo + self.Nb + self.V) / 5 +
                      5 * self.B)

        return self.C + A_C * alloy_term

    def preheat_en1011_2(
        self,
        heat_input: float,
        thickness: float,
        hydrogen: str = 'B'
    ) -> Tuple[float, str]:
        """Calculate preheat temperature per EN 1011-2 Method B.

        This uses a simplified approach based on CEN, plate thickness,
        heat input, and hydrogen level.

        Parameters
        ----------
        heat_input : float
            Heat input (kJ/mm)
        thickness : float
            Combined thickness (mm)
        hydrogen : str
            Hydrogen level ('A', 'B', 'C', 'D')

        Returns
        -------
        tuple of (preheat_temp_C, method_description)
        """
        cen = self.calculate_ce_cen()
        hd = HYDROGEN_LEVELS.get(hydrogen, 10.0)

        # EN 1011-2 Method B approximation
        # Thickness factor
        if thickness <= 10:
            t_factor = 0.0
        elif thickness <= 20:
            t_factor = 10.0
        elif thickness <= 30:
            t_factor = 25.0
        elif thickness <= 50:
            t_factor = 40.0
        else:
            t_factor = 60.0

        # CEN-based preheat (simplified from EN 1011-2 tables)
        if cen < 0.20:
            base_preheat = 0.0
        elif cen < 0.30:
            base_preheat = 20.0
        elif cen < 0.35:
            base_preheat = 50.0
        elif cen < 0.40:
            base_preheat = 75.0
        elif cen < 0.45:
            base_preheat = 100.0
        elif cen < 0.50:
            base_preheat = 125.0
        elif cen < 0.55:
            base_preheat = 150.0
        else:
            base_preheat = 200.0

        # Hydrogen adjustment
        if hydrogen == 'D':
            h_adjustment = 50.0
        elif hydrogen == 'C':
            h_adjustment = 25.0
        elif hydrogen == 'A':
            h_adjustment = -25.0
        else:
            h_adjustment = 0.0

        # Heat input adjustment (lower heat input → higher preheat needed)
        if heat_input < 0.5:
            hi_adjustment = 50.0
        elif heat_input < 1.0:
            hi_adjustment = 25.0
        elif heat_input > 3.0:
            hi_adjustment = -25.0
        else:
            hi_adjustment = 0.0

        preheat = base_preheat + t_factor + h_adjustment + hi_adjustment
        preheat = max(preheat, 0.0)  # No negative preheat

        method = f'EN 1011-2 Method B (CEN={cen:.3f}, t={thickness}mm, H={hydrogen})'
        return preheat, method

    def cracking_risk_assessment(
        self,
        preheat: float,
        heat_input: float,
        thickness: float,
        hydrogen: str = 'B',
        restraint: str = 'medium'
    ) -> Tuple[str, List[str]]:
        """Assess hydrogen-induced cracking risk.

        Parameters
        ----------
        preheat : float
            Applied preheat temperature (°C)
        heat_input : float
            Heat input (kJ/mm)
        thickness : float
            Plate thickness (mm)
        hydrogen : str
            Hydrogen level ('A', 'B', 'C', 'D')
        restraint : str
            Restraint level ('low', 'medium', 'high')

        Returns
        -------
        tuple of (risk_level, notes)
        """
        notes = []
        risk_score = 0

        cen = self.calculate_ce_cen()
        ce_iiw = self.ce_iiw

        # CE assessment
        if ce_iiw > 0.50:
            risk_score += 3
            notes.append(f'High CE(IIW) = {ce_iiw:.3f} (>0.50): high hardenability')
        elif ce_iiw > 0.40:
            risk_score += 2
            notes.append(f'Moderate CE(IIW) = {ce_iiw:.3f} (>0.40)')
        elif ce_iiw > 0.30:
            risk_score += 1
            notes.append(f'Low CE(IIW) = {ce_iiw:.3f}')
        else:
            notes.append(f'Very low CE(IIW) = {ce_iiw:.3f}: minimal hardenability concern')

        # Hydrogen level
        if hydrogen == 'D':
            risk_score += 3
            notes.append('High hydrogen (>20 ml/100g): use low-hydrogen consumables')
        elif hydrogen == 'C':
            risk_score += 2
            notes.append('Medium hydrogen (15 ml/100g): consider lower hydrogen process')

        # Thickness
        if thickness > 50:
            risk_score += 2
            notes.append(f'Thick section ({thickness}mm > 50mm): increased restraint stress')
        elif thickness > 30:
            risk_score += 1
            notes.append(f'Moderate thickness ({thickness}mm)')

        # Restraint
        if restraint == 'high':
            risk_score += 2
            notes.append('High restraint: consider higher preheat or PWHT')
        elif restraint == 'medium':
            risk_score += 1

        # Heat input (very low heat input with high CE is risky)
        if heat_input < 0.8 and ce_iiw > 0.35:
            risk_score += 2
            notes.append(f'Low heat input ({heat_input} kJ/mm) with elevated CE: fast cooling')

        # Preheat adequacy
        recommended, _ = self.preheat_en1011_2(heat_input, thickness, hydrogen)
        if preheat < recommended:
            risk_score += 2
            notes.append(
                f'Applied preheat ({preheat}°C) below recommended ({recommended:.0f}°C)'
            )
        elif preheat >= recommended + 25:
            risk_score -= 1
            notes.append(
                f'Applied preheat ({preheat}°C) exceeds recommended ({recommended:.0f}°C)'
            )

        # Determine risk level
        if risk_score <= 2:
            risk = 'low'
        elif risk_score <= 5:
            risk = 'medium'
        else:
            risk = 'high'

        return risk, notes

    def calculate(
        self,
        heat_input: float,
        thickness: float,
        hydrogen: str = 'B',
        restraint: str = 'medium',
        applied_preheat: Optional[float] = None,
    ) -> PreheatResult:
        """Run complete preheat calculation.

        Parameters
        ----------
        heat_input : float
            Heat input (kJ/mm)
        thickness : float
            Plate thickness (mm)
        hydrogen : str
            Hydrogen level ('A', 'B', 'C', 'D')
        restraint : str
            Restraint level ('low', 'medium', 'high')
        applied_preheat : float, optional
            Actual preheat to assess (defaults to recommended)

        Returns
        -------
        PreheatResult
        """
        result = PreheatResult()

        result.ce_iiw = self.ce_iiw
        result.ce_pcm = self.ce_pcm
        result.ce_cen = self.calculate_ce_cen()
        result.hydrogen_level = hydrogen
        result.plate_thickness_mm = thickness
        result.heat_input_kj_mm = heat_input

        # Get recommended preheat
        preheat_temp, method = self.preheat_en1011_2(heat_input, thickness, hydrogen)
        result.preheat_en1011_2 = preheat_temp
        result.preheat_method = method

        # Assess cracking risk
        check_preheat = applied_preheat if applied_preheat is not None else preheat_temp
        risk, notes = self.cracking_risk_assessment(
            check_preheat, heat_input, thickness, hydrogen, restraint
        )
        result.cracking_risk = risk
        result.cracking_notes = notes

        return result
