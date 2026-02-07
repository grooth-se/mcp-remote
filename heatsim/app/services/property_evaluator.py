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


class PropertyPlotter:
    """Generate plots for temperature-dependent material properties."""

    def __init__(self):
        """Initialize plotter with default styling."""
        self.figure_size = (8, 5)
        self.dpi = 100
        self.line_color = '#0d6efd'  # Bootstrap primary blue
        self.marker_color = '#dc3545'  # Bootstrap danger red
        self.grid_alpha = 0.3

    def plot_property(self, property_model, temp_range: tuple = None,
                      n_points: int = 100, show_data_points: bool = True) -> bytes:
        """Generate a plot of a temperature-dependent property.

        Parameters
        ----------
        property_model : MaterialProperty
            The property to plot
        temp_range : tuple, optional
            (min_temp, max_temp) range in °C. Auto-detected if None.
        n_points : int
            Number of interpolation points for smooth curve
        show_data_points : bool
            Whether to show original data points as markers

        Returns
        -------
        bytes
            PNG image data
        """
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from io import BytesIO

        evaluator = PropertyEvaluator(property_model)
        data = evaluator.data

        fig, ax = plt.subplots(figsize=self.figure_size, dpi=self.dpi)

        prop_type = property_model.property_type

        if prop_type == 'constant':
            # Just show a horizontal line
            value = data.get('value', 0)
            temp_range = temp_range or (0, 1000)
            temps = np.linspace(temp_range[0], temp_range[1], 10)
            values = [value] * len(temps)
            ax.axhline(y=value, color=self.line_color, linewidth=2, label='Constant')

        elif prop_type == 'curve':
            # Get original data points
            orig_temps = data.get('temperature', [])
            orig_values = data.get('value', [])

            if not orig_temps or not orig_values:
                return self._create_empty_plot(ax, fig, "No curve data available")

            # Determine temperature range
            if temp_range is None:
                temp_range = (min(orig_temps), max(orig_temps))

            # Generate smooth interpolated curve
            temps = np.linspace(temp_range[0], temp_range[1], n_points)
            values = [evaluator.evaluate(temperature=t) for t in temps]

            ax.plot(temps, values, color=self.line_color, linewidth=2, label='Interpolated')

            if show_data_points:
                ax.scatter(orig_temps, orig_values, color=self.marker_color,
                          s=50, zorder=5, label='Data points', edgecolors='white')

        elif prop_type == 'polynomial':
            # Evaluate polynomial over range
            temp_range = temp_range or (0, 1000)
            temps = np.linspace(temp_range[0], temp_range[1], n_points)
            values = [evaluator.evaluate(temperature=t) for t in temps]
            ax.plot(temps, values, color=self.line_color, linewidth=2, label='Polynomial fit')

        elif prop_type == 'equation':
            # Evaluate equation over range
            temp_range = temp_range or (0, 1000)
            temps = np.linspace(temp_range[0], temp_range[1], n_points)
            values = []
            for t in temps:
                v = evaluator.evaluate(temperature=t)
                values.append(v if v is not None else np.nan)
            ax.plot(temps, values, color=self.line_color, linewidth=2, label='Equation')

        else:
            return self._create_empty_plot(ax, fig, f"Unsupported property type: {prop_type}")

        # Styling
        ax.set_xlabel('Temperature (°C)', fontsize=11)
        units = property_model.units or ''
        ax.set_ylabel(f'{property_model.display_name} ({units})', fontsize=11)
        ax.set_title(f'{property_model.display_name} vs Temperature', fontsize=12, fontweight='bold')
        ax.grid(True, alpha=self.grid_alpha)
        ax.legend(loc='best', framealpha=0.9)

        plt.tight_layout()

        # Save to bytes
        buf = BytesIO()
        fig.savefig(buf, format='png', dpi=self.dpi, bbox_inches='tight',
                   facecolor='white', edgecolor='none')
        plt.close(fig)
        buf.seek(0)
        return buf.read()

    def plot_phase_properties(self, phase_properties: list, property_type: str = 'density') -> bytes:
        """Generate a bar chart comparing phase properties.

        Parameters
        ----------
        phase_properties : list
            List of PhaseProperty model instances
        property_type : str
            'density' or 'expansion' to select which property to plot

        Returns
        -------
        bytes
            PNG image data
        """
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from io import BytesIO

        fig, ax = plt.subplots(figsize=self.figure_size, dpi=self.dpi)

        if not phase_properties:
            return self._create_empty_plot(ax, fig, "No phase properties defined")

        # Define colors for each phase
        phase_colors = {
            'ferrite': '#4CAF50',      # Green
            'austenite': '#FF9800',    # Orange
            'martensite': '#F44336',   # Red
            'bainite': '#9C27B0',      # Purple
            'pearlite': '#3F51B5',     # Indigo
            'cementite': '#607D8B',    # Blue-grey
        }

        phases = []
        values = []
        colors = []

        for pp in phase_properties:
            if property_type == 'density' and pp.relative_density is not None:
                phases.append(pp.phase_label)
                values.append(pp.relative_density)
                colors.append(phase_colors.get(pp.phase, '#808080'))
            elif property_type == 'expansion' and pp.thermal_expansion_coeff is not None:
                phases.append(pp.phase_label)
                values.append(pp.thermal_expansion_coeff * 1e6)  # Convert to µ/K
                colors.append(phase_colors.get(pp.phase, '#808080'))

        if not phases:
            return self._create_empty_plot(ax, fig, f"No {property_type} data available")

        bars = ax.bar(phases, values, color=colors, edgecolor='white', linewidth=1.5)

        # Add value labels on bars
        for bar, val in zip(bars, values):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'{val:.4f}' if property_type == 'density' else f'{val:.1f}',
                   ha='center', va='bottom', fontsize=10)

        # Styling
        if property_type == 'density':
            ax.set_ylabel('Relative Density', fontsize=11)
            ax.set_title('Phase Relative Densities (Reference: Ferrite at 20°C = 1.0)',
                        fontsize=12, fontweight='bold')
        else:
            ax.set_ylabel('Thermal Expansion Coefficient (µm/m·K)', fontsize=11)
            ax.set_title('Phase Thermal Expansion Coefficients',
                        fontsize=12, fontweight='bold')

        ax.grid(True, alpha=self.grid_alpha, axis='y')
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()

        buf = BytesIO()
        fig.savefig(buf, format='png', dpi=self.dpi, bbox_inches='tight',
                   facecolor='white', edgecolor='none')
        plt.close(fig)
        buf.seek(0)
        return buf.read()

    def plot_expansion_vs_temperature(self, phase_properties: list,
                                       temp_range: tuple = (0, 900),
                                       n_points: int = 100) -> bytes:
        """Plot thermal expansion coefficient vs temperature for all phases.

        Parameters
        ----------
        phase_properties : list
            List of PhaseProperty model instances
        temp_range : tuple
            (min_temp, max_temp) in °C
        n_points : int
            Number of points for plotting

        Returns
        -------
        bytes
            PNG image data
        """
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from io import BytesIO

        fig, ax = plt.subplots(figsize=self.figure_size, dpi=self.dpi)

        if not phase_properties:
            return self._create_empty_plot(ax, fig, "No phase properties defined")

        phase_colors = {
            'ferrite': '#4CAF50',
            'austenite': '#FF9800',
            'martensite': '#F44336',
            'bainite': '#9C27B0',
            'pearlite': '#3F51B5',
            'cementite': '#607D8B',
        }

        temps = np.linspace(temp_range[0], temp_range[1], n_points)

        has_data = False
        for pp in phase_properties:
            if pp.thermal_expansion_coeff is None:
                continue

            has_data = True
            values = [pp.get_expansion_at_temperature(t) * 1e6 for t in temps]  # µ/K
            color = phase_colors.get(pp.phase, '#808080')
            linestyle = '--' if pp.is_expansion_temperature_dependent else '-'

            ax.plot(temps, values, color=color, linewidth=2,
                   label=pp.phase_label, linestyle=linestyle)

        if not has_data:
            return self._create_empty_plot(ax, fig, "No expansion data available")

        ax.set_xlabel('Temperature (°C)', fontsize=11)
        ax.set_ylabel('Thermal Expansion Coefficient (µm/m·K)', fontsize=11)
        ax.set_title('Thermal Expansion vs Temperature by Phase', fontsize=12, fontweight='bold')
        ax.grid(True, alpha=self.grid_alpha)
        ax.legend(loc='best', framealpha=0.9)

        plt.tight_layout()

        buf = BytesIO()
        fig.savefig(buf, format='png', dpi=self.dpi, bbox_inches='tight',
                   facecolor='white', edgecolor='none')
        plt.close(fig)
        buf.seek(0)
        return buf.read()

    def _create_empty_plot(self, ax, fig, message: str) -> bytes:
        """Create an empty plot with a message."""
        from io import BytesIO
        import matplotlib.pyplot as plt

        ax.text(0.5, 0.5, message, ha='center', va='center',
               fontsize=14, color='gray', transform=ax.transAxes)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')

        buf = BytesIO()
        fig.savefig(buf, format='png', dpi=self.dpi, bbox_inches='tight',
                   facecolor='white', edgecolor='none')
        plt.close(fig)
        buf.seek(0)
        return buf.read()
