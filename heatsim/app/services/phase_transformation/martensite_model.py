"""Koistinen-Marburger model for athermal martensite transformation.

The fraction of martensite formed is a function of undercooling below Ms:
    f_m = 1 - exp(-alpha * (Ms - T))

This is a standalone model class that can be used with either stored
MartensiteParameters or default values.
"""
import math
from typing import Optional


class KoistinenMarburgerModel:
    """Koistinen-Marburger athermal martensite transformation model.

    f_m(T) = 1 - exp(-alpha * (Ms - T))  for T < Ms
    f_m(T) = 0                            for T >= Ms

    Parameters
    ----------
    ms : float
        Martensite start temperature (deg C)
    mf : float, optional
        Martensite finish temperature (deg C). If provided, used for
        informational purposes; alpha controls the actual kinetics.
    alpha : float
        Rate parameter (1/K), default 0.011
    """

    # Default K-M coefficient (typical for low-alloy steels)
    DEFAULT_ALPHA = 0.011

    def __init__(self, ms: float, mf: Optional[float] = None,
                 alpha: float = DEFAULT_ALPHA):
        self.ms = ms
        self.mf = mf if mf is not None else ms - 215
        self.alpha = alpha

    def fraction_at_temperature(self, temperature: float) -> float:
        """Calculate martensite fraction at a given temperature.

        Parameters
        ----------
        temperature : float
            Current temperature in deg C

        Returns
        -------
        float
            Martensite fraction (0 to 1)
        """
        if temperature >= self.ms:
            return 0.0

        undercooling = self.ms - temperature
        f = 1.0 - math.exp(-self.alpha * undercooling)
        return min(max(f, 0.0), 1.0)

    def temperature_at_fraction(self, fraction: float) -> Optional[float]:
        """Calculate temperature at which a given fraction is reached.

        T = Ms - ln(1/(1-f)) / alpha

        Parameters
        ----------
        fraction : float
            Target martensite fraction (0 < f < 1)

        Returns
        -------
        float or None
            Temperature in deg C, or None if fraction is invalid
        """
        if fraction <= 0 or fraction >= 1:
            return None
        T = self.ms - math.log(1.0 / (1.0 - fraction)) / self.alpha
        return T

    def fraction_from_cooling(self, temperatures: 'np.ndarray',
                               austenite_remaining: float = 1.0) -> float:
        """Calculate final martensite fraction from a cooling curve.

        The K-M equation depends only on the minimum temperature reached,
        not on the cooling path (athermal transformation).

        Parameters
        ----------
        temperatures : np.ndarray
            Temperature array during cooling (deg C)
        austenite_remaining : float
            Fraction of austenite available for martensite transformation
            (after diffusional transformations)

        Returns
        -------
        float
            Martensite fraction (scaled by available austenite)
        """
        import numpy as np
        t_min = float(np.min(temperatures))
        f_max = self.fraction_at_temperature(t_min)
        return f_max * austenite_remaining

    @classmethod
    def from_composition(cls, composition: dict) -> 'KoistinenMarburgerModel':
        """Create model from steel composition using Andrews formula for Ms.

        Parameters
        ----------
        composition : dict
            Element weight percentages

        Returns
        -------
        KoistinenMarburgerModel
        """
        from .critical_temperatures import calc_ms, calc_mf
        C = composition.get('C', 0.0)
        Mn = composition.get('Mn', 0.0)
        Ni = composition.get('Ni', 0.0)
        Cr = composition.get('Cr', 0.0)
        Mo = composition.get('Mo', 0.0)
        Si = composition.get('Si', 0.0)

        ms = calc_ms(C, Mn, Ni, Cr, Mo, Si)
        mf = calc_mf(ms)
        return cls(ms=ms, mf=mf)
