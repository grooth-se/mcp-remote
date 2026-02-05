"""Property evaluation service.

Handles interpolation and evaluation of material properties based on type:
- constant: Single value
- curve: Temperature-dependent with linear interpolation
- table: Multi-variable lookup
- polynomial: Polynomial evaluation
- equation: Safe mathematical expression evaluation
"""
import json
import math
import re
from typing import Any, Optional, Union

import numpy as np
from scipy import interpolate


class PropertyEvaluator:
    """Evaluates material properties at specified conditions."""

    # Safe functions allowed in equation evaluation
    SAFE_FUNCTIONS = {
        'abs': abs,
        'min': min,
        'max': max,
        'sqrt': math.sqrt,
        'exp': math.exp,
        'log': math.log,
        'log10': math.log10,
        'sin': math.sin,
        'cos': math.cos,
        'tan': math.tan,
        'pow': pow,
    }

    def __init__(self, property_model):
        """Initialize with a MaterialProperty model instance.

        Parameters
        ----------
        property_model : MaterialProperty
            The property model to evaluate
        """
        self.property = property_model
        self._data = None
        self._interpolator = None

    @property
    def data(self) -> dict:
        """Lazy-load and cache parsed data."""
        if self._data is None:
            self._data = self.property.data_dict
        return self._data

    def evaluate(self, **conditions) -> Optional[float]:
        """Evaluate property at given conditions.

        Parameters
        ----------
        **conditions : dict
            Variable values, e.g., temperature=500, phase='austenite'

        Returns
        -------
        float or None
            Evaluated property value, or None if evaluation fails
        """
        prop_type = self.property.property_type

        if prop_type == 'constant':
            return self._eval_constant()
        elif prop_type == 'curve':
            return self._eval_curve(**conditions)
        elif prop_type == 'table':
            return self._eval_table(**conditions)
        elif prop_type == 'polynomial':
            return self._eval_polynomial(**conditions)
        elif prop_type == 'equation':
            return self._eval_equation(**conditions)
        else:
            return None

    def _eval_constant(self) -> Optional[float]:
        """Evaluate constant property."""
        return self.data.get('value')

    def _eval_curve(self, **conditions) -> Optional[float]:
        """Evaluate temperature-dependent curve using linear interpolation.

        Data format: {"temperature": [T1, T2, ...], "value": [V1, V2, ...]}
        """
        temp = conditions.get('temperature')
        if temp is None:
            return None

        temps = self.data.get('temperature', [])
        values = self.data.get('value', [])

        if not temps or not values or len(temps) != len(values):
            return None

        # Create interpolator on first use
        if self._interpolator is None:
            self._interpolator = interpolate.interp1d(
                temps, values,
                kind='linear',
                bounds_error=False,
                fill_value=(values[0], values[-1])  # Extrapolate with edge values
            )

        result = self._interpolator(temp)
        return float(result)

    def _eval_table(self, **conditions) -> Optional[float]:
        """Evaluate multi-variable table lookup.

        Data format: {
            "variables": ["temperature", "phase"],
            "temperature": [T1, T2, ...],
            "phase": ["austenite", "ferrite"],
            "values": [[v11, v12], [v21, v22], ...]  # [temp_idx][phase_idx]
        }
        """
        variables = self.data.get('variables', [])
        if not variables:
            return None

        # Get indices for each variable
        indices = []
        for var in variables:
            var_values = self.data.get(var, [])
            condition_value = conditions.get(var)

            if condition_value is None or not var_values:
                return None

            # For numeric variables, find nearest index
            if isinstance(var_values[0], (int, float)):
                idx = np.argmin(np.abs(np.array(var_values) - condition_value))
            else:
                # For categorical variables, exact match
                try:
                    idx = var_values.index(condition_value)
                except ValueError:
                    return None
            indices.append(idx)

        # Navigate to value in nested array
        values = self.data.get('values', [])
        try:
            result = values
            for idx in indices:
                result = result[idx]
            return float(result)
        except (IndexError, TypeError):
            return None

    def _eval_polynomial(self, **conditions) -> Optional[float]:
        """Evaluate polynomial.

        Data format: {
            "variable": "temperature",
            "coefficients": [a0, a1, a2, ...]  # a0 + a1*x + a2*x^2 + ...
        }
        """
        var_name = self.data.get('variable', 'temperature')
        coeffs = self.data.get('coefficients', [])
        x = conditions.get(var_name)

        if x is None or not coeffs:
            return None

        # Evaluate polynomial: a0 + a1*x + a2*x^2 + ...
        result = sum(c * (x ** i) for i, c in enumerate(coeffs))
        return float(result)

    def _eval_equation(self, **conditions) -> Optional[float]:
        """Evaluate mathematical equation safely.

        Data format: {
            "equation": "42.5 - 0.015*T",
            "variables": {"T": "temperature"}
        }
        """
        equation = self.data.get('equation', '')
        var_mapping = self.data.get('variables', {})

        if not equation:
            return None

        # Build safe evaluation namespace
        namespace = dict(self.SAFE_FUNCTIONS)

        # Map equation variables to condition values
        for eq_var, cond_var in var_mapping.items():
            value = conditions.get(cond_var)
            if value is None:
                return None
            namespace[eq_var] = value

        # Validate equation contains only allowed characters
        # Allow: numbers, operators, parentheses, dots, variable names, function names
        allowed_pattern = r'^[\d\s\+\-\*/\.\(\)a-zA-Z_]+$'
        if not re.match(allowed_pattern, equation):
            return None

        try:
            result = eval(equation, {"__builtins__": {}}, namespace)
            return float(result)
        except (SyntaxError, NameError, TypeError, ZeroDivisionError):
            return None


def evaluate_property(property_model, **conditions) -> Optional[float]:
    """Convenience function to evaluate a property.

    Parameters
    ----------
    property_model : MaterialProperty
        The property to evaluate
    **conditions : dict
        Evaluation conditions (e.g., temperature=500)

    Returns
    -------
    float or None
        Evaluated value
    """
    evaluator = PropertyEvaluator(property_model)
    return evaluator.evaluate(**conditions)
