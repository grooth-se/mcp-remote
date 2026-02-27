"""CCT curve prediction from steel chemical composition.

Uses the Li et al. (1998) Modified Kirkaldy model with empirical equations
to predict continuous cooling transformation (CCT) phase boundaries from
steel composition. Generates C-curves for ferrite, pearlite, and bainite
phases in the format expected by create_cct_overlay_plot().

References:
    - Li, M.V. et al. (1998) "A Computational Model for the Prediction of
      Steel Hardenability", Metallurgical and Materials Transactions B, 29B.
    - Andrews, K.W. (1965) "Empirical Formulae for the Calculation of Some
      Transformation Temperatures", JISI, 203, 721-727.
    - Steven, W. & Haynes, A.G. (1956) JISI, 183, 349-359.
"""

import math
import numpy as np


class CCTCurvePredictor:
    """Predict CCT phase transformation curves from steel composition.

    Uses empirical models (Andrews, Steven-Haynes, Li et al.) to compute
    transformation temperatures and C-curve shapes for ferrite, pearlite,
    and bainite phases.

    Args:
        composition: Dict of element weight percentages, e.g.
            {'C': 0.22, 'Mn': 0.45, 'Si': 0.25, 'Cr': 2.25, ...}
        transformation_temps: Optional dict of known transformation temps
            {'Ac1': 730, 'Ac3': 800, 'Ms': 290, 'Bs': 550, ...}
            If provided, these override the empirical calculations.
    """

    def __init__(self, composition, transformation_temps=None):
        self.comp = composition
        self.trans_temps = transformation_temps or {}

        # Extract elements with defaults of 0.0
        self.C = composition.get('C', 0.0)
        self.Mn = composition.get('Mn', 0.0)
        self.Si = composition.get('Si', 0.0)
        self.Cr = composition.get('Cr', 0.0)
        self.Ni = composition.get('Ni', 0.0)
        self.Mo = composition.get('Mo', 0.0)
        self.V = composition.get('V', 0.0)
        self.W = composition.get('W', 0.0)
        self.Cu = composition.get('Cu', 0.0)
        self.P = composition.get('P', 0.0)
        self.B = composition.get('B', 0.0)

        # Compute transformation temperatures
        self.Ae3 = self._calc_ae3()
        self.Ae1 = self._calc_ae1()
        self.Bs = self._calc_bs()
        self.Ms = self._calc_ms()

    def _calc_ae3(self):
        """Ae3 temperature using Andrews (1965) formula."""
        if 'Ac3' in self.trans_temps and self.trans_temps['Ac3']:
            return self.trans_temps['Ac3']
        C_sqrt = math.sqrt(max(self.C, 0.001))
        return (910 - 203 * C_sqrt - 15.2 * self.Ni + 44.7 * self.Si
                + 104 * self.V + 31.5 * self.Mo + 13.1 * self.W
                - 30 * self.Mn - 11 * self.Cr - 20 * self.Cu
                + 700 * self.P)

    def _calc_ae1(self):
        """Ae1 temperature using Andrews (1965) formula."""
        if 'Ac1' in self.trans_temps and self.trans_temps['Ac1']:
            return self.trans_temps['Ac1']
        return (727 - 10.7 * self.Mn - 16.9 * self.Ni + 29.1 * self.Si
                + 16.9 * self.Cr + 6.38 * self.W)

    def _calc_bs(self):
        """Bainite start temperature using Steven & Haynes (1956)."""
        if 'Bs' in self.trans_temps and self.trans_temps['Bs']:
            return self.trans_temps['Bs']
        return (830 - 270 * self.C - 90 * self.Mn - 37 * self.Ni
                - 70 * self.Cr - 83 * self.Mo)

    def _calc_ms(self):
        """Martensite start temperature using Andrews (1965)."""
        if 'Ms' in self.trans_temps and self.trans_temps['Ms']:
            return self.trans_temps['Ms']
        return (539 - 423 * self.C - 30.4 * self.Mn - 17.7 * self.Ni
                - 12.1 * self.Cr - 7.5 * self.Mo - 7.5 * self.Si)

    def _hardenability_factor(self):
        """Compute alloy hardenability multiplier (Grossmann-type approach).

        Higher values = more hardenable = C-curves shifted right (longer times).
        Each alloying element contributes a multiplicative factor calibrated
        against published CCT data for common steel grades.

        Typical values: plain carbon ~5-10, low-alloy ~15-30, Cr-Mo ~15-25.
        """
        # Carbon factor (from Grossmann ideal diameter correlation)
        f_C = 1.0 + 6.0 * self.C

        # Manganese: moderate hardenability effect
        f_Mn = 1.0 + 1.2 * self.Mn

        # Chromium: strong hardenability effect
        f_Cr = 1.0 + 0.6 * self.Cr

        # Molybdenum: strong hardenability effect
        f_Mo = 1.0 + 1.5 * self.Mo

        # Nickel: moderate hardenability effect
        f_Ni = 1.0 + 0.3 * self.Ni

        # Silicon: mild effect on hardenability
        f_Si = 1.0 + 0.3 * self.Si

        # Vanadium: moderate hardenability effect (in solution)
        f_V = 1.0 + 1.0 * self.V

        # Boron: potent hardenability element (even at ppm levels)
        f_B = 1.0 + 50.0 * self.B if self.B > 0 else 1.0

        return f_C * f_Mn * f_Cr * f_Mo * f_Ni * f_Si * f_V * f_B

    def _generate_c_curve(self, nose_temp, temp_range_above, temp_range_below,
                          base_time_nose, spread_factor=0.8):
        """Generate a single C-shaped transformation curve.

        The C-curve has a 'nose' (minimum incubation time) and times
        increase both above and below the nose temperature.

        Args:
            nose_temp: Temperature at the nose of the C-curve (°C).
            temp_range_above: Temperature range above nose to generate.
            temp_range_below: Temperature range below nose to generate.
            base_time_nose: Time at the nose (seconds).
            spread_factor: Controls how quickly time increases away from nose.

        Returns:
            List of [time, temperature] pairs sorted by temperature descending.
        """
        points = []
        n_points = 25

        # Upper branch (above nose)
        if temp_range_above > 5:
            temps_above = np.linspace(nose_temp, nose_temp + temp_range_above, n_points)
            for T in temps_above:
                dT = T - nose_temp
                # Time increases quadratically away from nose
                time = base_time_nose * (1.0 + spread_factor * (dT / temp_range_above) ** 2
                                         * (temp_range_above / 50.0))
                points.append([float(time), float(T)])

        # Lower branch (below nose)
        if temp_range_below > 5:
            temps_below = np.linspace(nose_temp, nose_temp - temp_range_below, n_points)
            for T in temps_below:
                dT = nose_temp - T
                time = base_time_nose * (1.0 + spread_factor * (dT / temp_range_below) ** 2
                                         * (temp_range_below / 50.0))
                points.append([float(time), float(T)])

        # Sort by temperature descending (high temp to low temp)
        points.sort(key=lambda p: -p[1])

        # Remove duplicate temperatures
        seen = set()
        unique = []
        for p in points:
            t_rounded = round(p[1], 1)
            if t_rounded not in seen:
                seen.add(t_rounded)
                unique.append(p)

        return unique

    def predict(self):
        """Predict CCT curves for all applicable phases.

        Returns:
            Dict with phase keys, each containing 'start' and 'finish' curves:
            {
                'ferrite': {'start': [[t,T], ...], 'finish': [[t,T], ...]},
                'pearlite': {'start': [...], 'finish': [...]},
                'bainite': {'start': [...], 'finish': [...]}
            }
        """
        hf = self._hardenability_factor()
        curves = {}

        # Ferrite: forms below Ae3, nose typically around 680-720°C
        if self.C < 0.8 and self.Ae3 > self.Ae1:
            curves['ferrite'] = self._predict_ferrite(hf)

        # Pearlite: forms below Ae1, nose typically around 550-650°C
        curves['pearlite'] = self._predict_pearlite(hf)

        # Bainite: forms below Bs, nose typically around 400-500°C
        if self.Bs > self.Ms + 20:
            curves['bainite'] = self._predict_bainite(hf)

        return curves

    def _predict_ferrite(self, hardenability_factor):
        """Predict ferrite transformation C-curves.

        During continuous cooling, ferrite nucleation requires undercooling
        below equilibrium Ae1.  Alloy additions (Cr, Mo, Mn) increase the
        undercooling and suppress diffusional ferrite.  The C-curve nose
        sits well below Ae1 for alloy steels and the region extends up
        toward Ae1 at long times, staying below the eutectoid temperature.
        """
        # Undercooling below Ae1 — Cr and Mo strongly suppress ferrite
        undercooling = 30 + 10 * self.Cr + 10 * self.Mo + 5 * self.Mn
        nose_temp = self.Ae1 - undercooling

        # Clamp: nose must stay above Bs + 30 (below that is bainite territory)
        nose_temp = max(nose_temp, self.Bs + 30)

        # Base time at nose for plain carbon steel ~1-5 seconds
        # Alloy additions shift it right
        base_time = 1.5 * hardenability_factor

        # Temperature ranges
        range_above = self.Ae1 - nose_temp  # Extends up toward Ae1
        range_below_raw = nose_temp - self.Bs - 20  # Down toward bainite
        range_below = min(max(range_below_raw, 50), 150)

        start_curve = self._generate_c_curve(
            nose_temp, range_above, range_below,
            base_time, spread_factor=0.9
        )

        # Finish curve: shifted right by factor 3-8x depending on composition
        finish_time_mult = 3.0 + 2.0 * self.C + 1.0 * self.Mn
        finish_time = base_time * finish_time_mult

        # Finish temperature range is slightly narrower
        finish_curve = self._generate_c_curve(
            nose_temp - 15, max(range_above - 10, 10), max(range_below - 15, 10),
            finish_time, spread_factor=1.0
        )

        return {'start': start_curve, 'finish': finish_curve}

    def _predict_pearlite(self, hardenability_factor):
        """Predict pearlite transformation C-curves."""
        # Pearlite nose: typically 50-100°C below Ae1
        nose_temp = self.Ae1 - 70

        # Pearlite is slower than ferrite; higher alloy -> much slower
        # Cr and Mo are particularly effective at retarding pearlite
        pearlite_retard = (1.0 + 0.8 * self.Cr) * (1.0 + 1.2 * self.Mo)
        base_time = 3.0 * hardenability_factor * pearlite_retard / max(self.C, 0.15)

        # Temperature ranges
        range_above = self.Ae1 - nose_temp + 5  # Just below Ae1
        range_below = nose_temp - max(self.Bs + 20, 450)  # Down toward Bs

        start_curve = self._generate_c_curve(
            nose_temp, range_above, max(range_below, 10),
            base_time, spread_factor=0.85
        )

        # Finish curve
        finish_time_mult = 4.0 + 3.0 * self.C
        finish_time = base_time * finish_time_mult

        finish_curve = self._generate_c_curve(
            nose_temp - 20, max(range_above - 15, 5), max(range_below - 20, 10),
            finish_time, spread_factor=0.95
        )

        return {'start': start_curve, 'finish': finish_curve}

    def _predict_bainite(self, hardenability_factor):
        """Predict bainite transformation C-curves."""
        # Bainite nose: midway between Bs and Ms
        nose_temp = self.Ms + 0.5 * (self.Bs - self.Ms)

        # Bainite kinetics: Mo strongly retards, Cr moderately
        bainite_retard = (1.0 + 0.8 * self.Cr) * (1.0 + 1.5 * self.Mo)
        base_time = 0.5 * hardenability_factor * bainite_retard

        # Temperature ranges
        range_above = self.Bs - nose_temp  # Up to Bs
        range_below = nose_temp - self.Ms - 10  # Down to near Ms

        start_curve = self._generate_c_curve(
            nose_temp, max(range_above, 10), max(range_below, 10),
            base_time, spread_factor=0.7
        )

        # Finish curve: shifted right
        finish_time_mult = 3.5 + 2.5 * self.C + 1.5 * self.Mn
        finish_time = base_time * finish_time_mult

        finish_curve = self._generate_c_curve(
            nose_temp - 10, max(range_above - 10, 10), max(range_below - 15, 10),
            finish_time, spread_factor=0.8
        )

        return {'start': start_curve, 'finish': finish_curve}


def predict_cct_curves(composition, transformation_temps=None):
    """Convenience function to predict CCT curves from composition.

    Args:
        composition: Dict of element weight percentages from
            SteelComposition.to_dict().
        transformation_temps: Optional dict of known transformation
            temperatures from PhaseDiagram.temps_dict.

    Returns:
        Dict with CCT curves in the format expected by
        create_cct_overlay_plot(), or None if prediction fails.
    """
    if not composition or not composition.get('C'):
        return None

    try:
        predictor = CCTCurvePredictor(composition, transformation_temps)
        curves = predictor.predict()
        return curves if curves else None
    except Exception:
        return None
