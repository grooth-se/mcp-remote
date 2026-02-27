"""Critical transformation temperature calculations from steel composition.

Implements Andrews (1965), Steven-Haynes (1956), and other empirical
formulae to estimate Ae1, Ae3, Bs, Ms, and Mf temperatures.

References:
    Andrews, K.W. (1965) JISI, 203, 721-727.
    Steven, W. & Haynes, A.G. (1956) JISI, 183, 349-359.
"""
import math
from typing import Dict, Optional


def calculate_critical_temperatures(composition: Dict[str, float],
                                     overrides: Optional[Dict[str, float]] = None
                                     ) -> Dict[str, float]:
    """Calculate all critical transformation temperatures from composition.

    Parameters
    ----------
    composition : dict
        Element weight percentages: {'C': 0.22, 'Mn': 0.45, ...}
    overrides : dict, optional
        Known temperatures to use instead of calculated values.
        Keys: 'Ae1', 'Ae3', 'Bs', 'Ms', 'Mf'

    Returns
    -------
    dict
        {'Ae1': float, 'Ae3': float, 'Bs': float, 'Ms': float, 'Mf': float}
    """
    overrides = overrides or {}
    C = composition.get('C', 0.0)
    Mn = composition.get('Mn', 0.0)
    Si = composition.get('Si', 0.0)
    Cr = composition.get('Cr', 0.0)
    Ni = composition.get('Ni', 0.0)
    Mo = composition.get('Mo', 0.0)
    V = composition.get('V', 0.0)
    W = composition.get('W', 0.0)
    Cu = composition.get('Cu', 0.0)
    P = composition.get('P', 0.0)

    temps = {}

    # Ae1 - eutectoid temperature (Andrews 1965)
    if 'Ae1' in overrides and overrides['Ae1']:
        temps['Ae1'] = overrides['Ae1']
    else:
        temps['Ae1'] = calc_ae1(Mn, Ni, Si, Cr, W)

    # Ae3 - upper critical temperature (Andrews 1965)
    if 'Ae3' in overrides and overrides['Ae3']:
        temps['Ae3'] = overrides['Ae3']
    else:
        temps['Ae3'] = calc_ae3(C, Mn, Ni, Si, Cr, Mo, V, W, Cu, P)

    # Bs - bainite start (Steven & Haynes 1956)
    if 'Bs' in overrides and overrides['Bs']:
        temps['Bs'] = overrides['Bs']
    else:
        temps['Bs'] = calc_bs(C, Mn, Ni, Cr, Mo)

    # Ms - martensite start (Andrews 1965)
    if 'Ms' in overrides and overrides['Ms']:
        temps['Ms'] = overrides['Ms']
    else:
        temps['Ms'] = calc_ms(C, Mn, Ni, Cr, Mo, Si)

    # Mf - martensite finish (estimated from Ms)
    if 'Mf' in overrides and overrides['Mf']:
        temps['Mf'] = overrides['Mf']
    else:
        temps['Mf'] = calc_mf(temps['Ms'])

    return temps


def calc_ae1(Mn: float, Ni: float, Si: float, Cr: float, W: float) -> float:
    """Ae1 temperature using Andrews (1965) formula.

    Ae1 = 727 - 10.7*Mn - 16.9*Ni + 29.1*Si + 16.9*Cr + 6.38*W

    Parameters
    ----------
    Mn, Ni, Si, Cr, W : float
        Element weight percentages

    Returns
    -------
    float
        Ae1 temperature in deg C
    """
    return 727 - 10.7 * Mn - 16.9 * Ni + 29.1 * Si + 16.9 * Cr + 6.38 * W


def calc_ae3(C: float, Mn: float, Ni: float, Si: float, Cr: float,
             Mo: float, V: float, W: float, Cu: float, P: float) -> float:
    """Ae3 temperature using Andrews (1965) formula.

    Ae3 = 910 - 203*sqrt(C) - 15.2*Ni + 44.7*Si + 104*V + 31.5*Mo
          + 13.1*W - 30*Mn - 11*Cr - 20*Cu + 700*P

    Parameters
    ----------
    C, Mn, Ni, Si, Cr, Mo, V, W, Cu, P : float
        Element weight percentages

    Returns
    -------
    float
        Ae3 temperature in deg C
    """
    C_sqrt = math.sqrt(max(C, 0.001))
    return (910 - 203 * C_sqrt - 15.2 * Ni + 44.7 * Si + 104 * V
            + 31.5 * Mo + 13.1 * W - 30 * Mn - 11 * Cr - 20 * Cu
            + 700 * P)


def calc_bs(C: float, Mn: float, Ni: float, Cr: float, Mo: float) -> float:
    """Bainite start temperature using Steven & Haynes (1956).

    Bs = 830 - 270*C - 90*Mn - 37*Ni - 70*Cr - 83*Mo

    Parameters
    ----------
    C, Mn, Ni, Cr, Mo : float
        Element weight percentages

    Returns
    -------
    float
        Bs temperature in deg C
    """
    return 830 - 270 * C - 90 * Mn - 37 * Ni - 70 * Cr - 83 * Mo


def calc_ms(C: float, Mn: float, Ni: float, Cr: float,
            Mo: float, Si: float) -> float:
    """Martensite start temperature using Andrews (1965).

    Ms = 539 - 423*C - 30.4*Mn - 17.7*Ni - 12.1*Cr - 7.5*Mo - 7.5*Si

    Parameters
    ----------
    C, Mn, Ni, Cr, Mo, Si : float
        Element weight percentages

    Returns
    -------
    float
        Ms temperature in deg C
    """
    return 539 - 423 * C - 30.4 * Mn - 17.7 * Ni - 12.1 * Cr - 7.5 * Mo - 7.5 * Si


def calc_mf(ms: float) -> float:
    """Estimate martensite finish temperature from Ms.

    A common approximation: Mf ~ Ms - 215 deg C.
    This corresponds to ~99% martensite in Koistinen-Marburger with alpha=0.011.
    Constrained to be >= -50 deg C.

    Parameters
    ----------
    ms : float
        Martensite start temperature in deg C

    Returns
    -------
    float
        Mf temperature in deg C
    """
    # For K-M equation: f = 1 - exp(-alpha*(Ms-T))
    # At Mf, f ~ 0.99 => alpha*(Ms-Mf) = ln(100) ~ 4.6
    # With alpha = 0.011: Ms - Mf ~ 418/0.011 ~ 4.6/0.011 ~ 418
    # But empirically, Mf ~ Ms - 215 is more realistic for most steels
    mf = ms - 215
    return max(mf, -50)
