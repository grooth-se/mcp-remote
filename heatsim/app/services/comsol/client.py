"""COMSOL client interface using mph library.

Provides connection management and basic operations for interacting
with a local COMSOL Multiphysics installation.

Singleton pattern: the COMSOL server starts once and is reused across
simulation runs (startup takes 30-60s).
"""
import os
import logging
import threading
from pathlib import Path
from typing import Optional, List, Dict, Any

import numpy as np

logger = logging.getLogger(__name__)

# Singleton lock and instance
_singleton_lock = threading.Lock()
_singleton_client = None


class COMSOLError(Exception):
    """Base exception for COMSOL-related errors."""
    pass


class COMSOLNotAvailableError(COMSOLError):
    """Raised when COMSOL is not installed or not accessible."""
    pass


def get_shared_client(comsol_path: Optional[str] = None) -> 'COMSOLClient':
    """Get or create the singleton COMSOLClient.

    The COMSOL server process is expensive to start (30-60s), so we
    reuse a single client across simulation runs.

    Parameters
    ----------
    comsol_path : str, optional
        Path to COMSOL installation

    Returns
    -------
    COMSOLClient
        Connected singleton client
    """
    global _singleton_client
    with _singleton_lock:
        if _singleton_client is None or not _singleton_client._connected:
            _singleton_client = COMSOLClient(comsol_path)
            _singleton_client.connect()
        return _singleton_client


def shutdown_shared_client():
    """Shut down the singleton COMSOL client."""
    global _singleton_client
    with _singleton_lock:
        if _singleton_client is not None:
            _singleton_client.disconnect()
            _singleton_client = None


class COMSOLClient:
    """Interface to local COMSOL installation via mph library.

    Uses the mph library to connect to COMSOL Multiphysics and perform
    operations like creating models, importing geometry, and running studies.

    Parameters
    ----------
    comsol_path : str, optional
        Path to COMSOL installation directory. If not specified, uses
        COMSOL_PATH env var or the Flask config default.
    """

    def __init__(self, comsol_path: Optional[str] = None):
        self._client = None
        self._comsol_path = comsol_path or os.environ.get(
            'COMSOL_PATH', '/Applications/COMSOL64/Multiphysics'
        )
        self._connected = False

    @property
    def is_available(self) -> bool:
        """Check if COMSOL/mph is available."""
        try:
            import mph
            return True
        except ImportError:
            return False

    def connect(self) -> None:
        """Establish connection to COMSOL server.

        Sets mph's comsolroot option before starting the server so it
        finds the correct installation.

        Raises
        ------
        COMSOLNotAvailableError
            If mph library is not installed or COMSOL cannot be found
        COMSOLError
            If connection to COMSOL fails
        """
        if self._connected:
            return

        try:
            import mph
        except ImportError:
            raise COMSOLNotAvailableError(
                "mph library not installed. Install with: pip install mph"
            )

        try:
            logger.info("Starting COMSOL connection...")

            # Set COMSOL root path before starting
            if self._comsol_path and Path(self._comsol_path).exists():
                mph.option('classkit', False)
                # Verify the COMSOL installation is discoverable
                try:
                    backend = mph.discovery.backend()
                    discovered_root = backend.get('root')
                    if discovered_root:
                        logger.info("Discovered COMSOL %s at %s",
                                    backend.get('name', '?'), discovered_root)
                    else:
                        logger.info("No COMSOL auto-discovered, using %s", self._comsol_path)
                except Exception as e:
                    logger.warning("COMSOL discovery failed: %s", e)

            self._client = mph.start(cores=4)
            self._connected = True
            logger.info("COMSOL connection established (server PID: %s)",
                        getattr(self._client, 'port', 'unknown'))
        except Exception as e:
            raise COMSOLError(f"Failed to connect to COMSOL: {e}")

    def disconnect(self) -> None:
        """Close connection to COMSOL server.

        Removes all loaded models before closing.
        """
        if self._client is not None:
            try:
                # Remove all loaded models to free memory
                self._client.clear()
            except Exception:
                pass
            self._client = None
            self._connected = False
            logger.info("COMSOL connection closed")

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
        return False

    @property
    def client(self):
        """Get the mph client, connecting if necessary."""
        if not self._connected:
            self.connect()
        return self._client

    def create_model(self, name: str = 'Untitled') -> Any:
        """Create a new empty COMSOL model."""
        model = self.client.create(name)
        logger.info("Created new COMSOL model: %s", name)
        return model

    def remove_model(self, model: Any) -> None:
        """Remove a model from the COMSOL server to free memory."""
        try:
            self.client.remove(model)
            logger.info("Removed COMSOL model")
        except Exception as e:
            logger.warning("Failed to remove model: %s", e)

    def load_model(self, filepath: str) -> Any:
        """Load an existing COMSOL model from .mph file."""
        path = Path(filepath)
        if not path.exists():
            raise COMSOLError(f"Model file not found: {filepath}")
        try:
            model = self.client.load(str(path))
            logger.info("Loaded COMSOL model from: %s", filepath)
            return model
        except Exception as e:
            raise COMSOLError(f"Failed to load model: {e}")

    def save_model(self, model: Any, filepath: str) -> None:
        """Save model to .mph file."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            model.save(str(path))
            logger.info("Saved COMSOL model to: %s", filepath)
        except Exception as e:
            raise COMSOLError(f"Failed to save model: {e}")

    def import_cad(self, model: Any, cad_data: bytes, filename: str,
                   format: str = 'step') -> List[str]:
        """Import CAD geometry into model."""
        import tempfile

        suffix = f'.{format}'
        if format == 'step':
            suffix = '.stp'
        elif format == 'iges':
            suffix = '.igs'

        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                f.write(cad_data)
                temp_path = f.name

            geom = model/'geometries'/'geom1'
            if geom is None:
                model.java.component().create('comp1', True)
                model.java.component('comp1').geom().create('geom1', 3)

            imp = model.java.component('comp1').geom('geom1').create('imp1', 'Import')
            imp.set('filename', temp_path)
            imp.set('type', format.upper())
            model.build()

            bodies = []
            logger.info("Imported CAD geometry from %s", filename)
            return bodies
        except Exception as e:
            raise COMSOLError(f"Failed to import CAD: {e}")
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass

    def run_study(self, model: Any, study_name: str = 'std1') -> None:
        """Execute a study in the model.

        Uses the Java API directly because mph's model.solve() may not
        find studies created via the Java API.
        """
        try:
            logger.info("Running study: %s", study_name)
            # Try Java API directly first (works for studies created via Java)
            try:
                model.java.study(study_name).run()
            except Exception:
                # Fall back to mph's solve()
                model.solve(study_name)
            logger.info("Study %s completed", study_name)
        except Exception as e:
            raise COMSOLError(f"Study execution failed: {e}")

    def get_parameter(self, model: Any, name: str) -> Any:
        """Get a parameter value from the model."""
        try:
            return model.parameter(name)
        except Exception:
            return None

    def set_parameter(self, model: Any, name: str, value: Any,
                      description: str = '') -> None:
        """Set a parameter in the model."""
        try:
            model.parameter(name, value, description)
            logger.debug("Set parameter %s = %s", name, value)
        except Exception as e:
            raise COMSOLError(f"Failed to set parameter {name}: {e}")

    def evaluate(self, model: Any, expression: str,
                 dataset: str = None) -> Any:
        """Evaluate an expression in the model."""
        try:
            if dataset:
                return model.evaluate(expression, dataset)
            return model.evaluate(expression)
        except Exception as e:
            raise COMSOLError(f"Evaluation failed for '{expression}': {e}")

    def evaluate_at_coordinates(self, model: Any,
                                 expression: str,
                                 coordinates: List[List[float]],
                                 dataset_name: str = 'probe_pts') -> np.ndarray:
        """Evaluate expression at specific coordinates via cut-point dataset.

        Creates a CutPoint dataset at the given coordinates, evaluates
        the expression, then removes the dataset.

        Parameters
        ----------
        model : Model
            COMSOL model with completed solution
        expression : str
            Expression to evaluate (e.g., 'T')
        coordinates : list of [x, y, z]
            Coordinates in meters
        dataset_name : str
            Name for the temporary dataset

        Returns
        -------
        np.ndarray
            Evaluated values at each coordinate, shape (n_coords, n_times)
        """
        try:
            java = model.java
            # Create cut-point dataset
            ds = java.result().dataset().create(dataset_name, 'CutPoint3D')
            # Set coordinates
            x_coords = ' '.join(str(c[0]) for c in coordinates)
            y_coords = ' '.join(str(c[1]) for c in coordinates)
            z_coords = ' '.join(str(c[2]) for c in coordinates)
            ds.set('pointx', x_coords)
            ds.set('pointy', y_coords)
            ds.set('pointz', z_coords)

            # Evaluate
            result = model.evaluate(expression, dataset_name)

            # Clean up
            java.result().dataset().remove(dataset_name)

            return np.array(result)
        except Exception as e:
            # Try cleanup
            try:
                model.java.result().dataset().remove(dataset_name)
            except Exception:
                pass
            raise COMSOLError(f"Coordinate evaluation failed: {e}")

    def export_vtk_at_time(self, model: Any, filepath: str,
                            time_value: float,
                            expression: str = 'T') -> None:
        """Export VTK file at a specific solution time step.

        Parameters
        ----------
        model : Model
            COMSOL model with completed solution
        filepath : str
            Output VTK file path
        time_value : float
            Solution time to export (seconds)
        expression : str
            Expression to export
        """
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            java = model.java

            # Create VTK export node
            export_tag = 'vtk_export'
            try:
                java.result().export().remove(export_tag)
            except Exception:
                pass

            # Use VTK export type directly (COMSOL 6.x)
            exp = java.result().export().create(export_tag, 'Data')
            exp.set('expr', [expression])
            # Set filename with .vtu extension (COMSOL 6.x exports VTK as VTU)
            vtk_path = str(path)
            if vtk_path.endswith('.vtk'):
                vtk_path = vtk_path[:-4] + '.vtu'
            exp.set('filename', vtk_path)

            # Set time selection
            exp.set('timeinterp', 'on')
            exp.set('t', str(time_value))

            exp.run()

            # Clean up export node
            java.result().export().remove(export_tag)

            logger.info("Exported VTK at t=%.1fs to: %s", time_value, filepath)
        except Exception as e:
            try:
                model.java.result().export().remove('vtk_export')
            except Exception:
                pass
            raise COMSOLError(f"VTK export failed: {e}")

    def export_data(self, model: Any, filename: str,
                    expression: str = 'T',
                    format: str = 'vtk') -> None:
        """Export solution data to file."""
        try:
            path = Path(filename)
            path.parent.mkdir(parents=True, exist_ok=True)

            exp = model.java.result().export().create('data1', 'Data')
            exp.set('expr', expression)
            exp.set('filename', str(path))
            exp.run()

            # Clean up
            model.java.result().export().remove('data1')
            logger.info("Exported data to: %s", filename)
        except Exception as e:
            raise COMSOLError(f"Export failed: {e}")

    def get_names(self, model: Any, node_type: str) -> List[str]:
        """Get names of nodes of a specific type."""
        try:
            names = []
            if node_type == 'physics':
                node = model/'physics'
            elif node_type == 'study':
                node = model/'studies'
            elif node_type == 'geometry':
                node = model/'geometries'
            elif node_type == 'material':
                node = model/'materials'
            else:
                return []

            if node:
                names = list(node.keys())
            return names
        except Exception:
            return []


class MockCOMSOLClient(COMSOLClient):
    """Mock COMSOL client for testing without actual COMSOL installation."""

    def __init__(self, comsol_path: Optional[str] = None):
        super().__init__(comsol_path)
        self._models: Dict[str, dict] = {}
        self._connected = True

    @property
    def is_available(self) -> bool:
        return True

    def connect(self) -> None:
        self._connected = True
        logger.info("Mock COMSOL connection established")

    def disconnect(self) -> None:
        self._connected = False
        logger.info("Mock COMSOL connection closed")

    def create_model(self, name: str = 'Untitled') -> dict:
        model = {
            'name': name,
            'parameters': {},
            'geometries': {},
            'physics': {},
            'studies': {},
            'results': {},
        }
        self._models[name] = model
        logger.info("Created mock COMSOL model: %s", name)
        return model

    def remove_model(self, model: Any) -> None:
        name = model.get('name', '') if isinstance(model, dict) else str(model)
        self._models.pop(name, None)
        logger.info("Removed mock model")

    def load_model(self, filepath: str) -> dict:
        path = Path(filepath)
        if not path.exists():
            raise COMSOLError(f"Model file not found: {filepath}")
        return self.create_model(path.stem)

    def save_model(self, model: dict, filepath: str) -> None:
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("Mock saved model to: %s", filepath)

    def import_cad(self, model: dict, cad_data: bytes, filename: str,
                   format: str = 'step') -> List[str]:
        bodies = ['string_1', 'string_2', 'string_3', 'base_plate']
        model['geometries']['cad'] = {'bodies': bodies}
        logger.info("Mock imported CAD with %d bodies", len(bodies))
        return bodies

    def run_study(self, model: dict, study_name: str = 'std1') -> None:
        logger.info("Mock running study: %s", study_name)
        model['results'][study_name] = {'completed': True}

    def get_parameter(self, model: dict, name: str) -> Any:
        return model.get('parameters', {}).get(name)

    def set_parameter(self, model: dict, name: str, value: Any,
                      description: str = '') -> None:
        if 'parameters' not in model:
            model['parameters'] = {}
        model['parameters'][name] = {'value': value, 'description': description}

    def evaluate(self, model: dict, expression: str,
                 dataset: str = None) -> Any:
        return np.linspace(1500, 100, 100)

    def evaluate_at_coordinates(self, model: Any,
                                 expression: str,
                                 coordinates: List[List[float]],
                                 dataset_name: str = 'probe_pts') -> np.ndarray:
        n_coords = len(coordinates)
        n_times = 100
        # Mock: generate different cooling curves per position
        result = np.zeros((n_coords, n_times))
        for i in range(n_coords):
            # Surface cools faster than center
            rate_factor = 1.0 + 0.5 * i / max(n_coords - 1, 1)
            result[i] = 900 * np.exp(-0.01 * rate_factor * np.arange(n_times))
        return result

    def export_vtk_at_time(self, model: Any, filepath: str,
                            time_value: float,
                            expression: str = 'T') -> None:
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        logger.info("Mock VTK export at t=%.1fs to: %s", time_value, filepath)

    def export_data(self, model: dict, filename: str,
                    expression: str = 'T',
                    format: str = 'vtk') -> None:
        path = Path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        logger.info("Mock exported to: %s", filename)
