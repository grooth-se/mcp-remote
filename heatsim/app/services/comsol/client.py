"""COMSOL client interface using mph library.

Provides connection management and basic operations for interacting
with a local COMSOL Multiphysics installation.
"""
import os
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class COMSOLError(Exception):
    """Base exception for COMSOL-related errors."""
    pass


class COMSOLNotAvailableError(COMSOLError):
    """Raised when COMSOL is not installed or not accessible."""
    pass


class COMSOLClient:
    """Interface to local COMSOL installation via mph library.

    Uses the mph library to connect to COMSOL Multiphysics and perform
    operations like creating models, importing geometry, and running studies.

    Parameters
    ----------
    comsol_path : str, optional
        Path to COMSOL installation directory. If not specified, mph will
        attempt to find COMSOL automatically.

    Attributes
    ----------
    client : mph.Client
        The mph client connection to COMSOL
    """

    def __init__(self, comsol_path: Optional[str] = None):
        """Initialize COMSOL client connection.

        Parameters
        ----------
        comsol_path : str, optional
            Path to COMSOL installation. If None, uses environment variable
            COMSOL_PATH or lets mph auto-detect.
        """
        self._client = None
        self._comsol_path = comsol_path or os.environ.get('COMSOL_PATH')
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
            if self._comsol_path:
                self._client = mph.start(cores=4)  # mph finds COMSOL automatically
            else:
                self._client = mph.start(cores=4)
            self._connected = True
            logger.info("COMSOL connection established")
        except Exception as e:
            raise COMSOLError(f"Failed to connect to COMSOL: {e}")

    def disconnect(self) -> None:
        """Close connection to COMSOL server."""
        if self._client is not None:
            try:
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
        """Create a new empty COMSOL model.

        Parameters
        ----------
        name : str
            Name for the model

        Returns
        -------
        Model
            mph Model object
        """
        model = self.client.create(name)
        logger.info(f"Created new COMSOL model: {name}")
        return model

    def load_model(self, filepath: str) -> Any:
        """Load an existing COMSOL model from .mph file.

        Parameters
        ----------
        filepath : str
            Path to .mph file

        Returns
        -------
        Model
            mph Model object

        Raises
        ------
        COMSOLError
            If file doesn't exist or cannot be loaded
        """
        path = Path(filepath)
        if not path.exists():
            raise COMSOLError(f"Model file not found: {filepath}")

        try:
            model = self.client.load(str(path))
            logger.info(f"Loaded COMSOL model from: {filepath}")
            return model
        except Exception as e:
            raise COMSOLError(f"Failed to load model: {e}")

    def save_model(self, model: Any, filepath: str) -> None:
        """Save model to .mph file.

        Parameters
        ----------
        model : Model
            mph Model object to save
        filepath : str
            Output path for .mph file
        """
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            model.save(str(path))
            logger.info(f"Saved COMSOL model to: {filepath}")
        except Exception as e:
            raise COMSOLError(f"Failed to save model: {e}")

    def import_cad(self, model: Any, cad_data: bytes, filename: str,
                   format: str = 'step') -> List[str]:
        """Import CAD geometry into model.

        Parameters
        ----------
        model : Model
            mph Model object
        cad_data : bytes
            CAD file content
        filename : str
            Original filename for the CAD file
        format : str
            CAD format: 'step', 'iges', 'stl'

        Returns
        -------
        list of str
            List of body/domain names imported from CAD

        Raises
        ------
        COMSOLError
            If import fails
        """
        import tempfile

        # Write CAD data to temporary file
        suffix = f'.{format}'
        if format == 'step':
            suffix = '.stp'
        elif format == 'iges':
            suffix = '.igs'

        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                f.write(cad_data)
                temp_path = f.name

            # Import into COMSOL
            # Access the geometry node and create an import
            geom = model/'geometries'/'geom1'
            if geom is None:
                # Create geometry sequence
                model.java.component().create('comp1', True)
                model.java.component('comp1').geom().create('geom1', 3)
                geom = model/'geometries'/'geom1'

            # Create CAD import node
            imp = model.java.component('comp1').geom('geom1').create('imp1', 'Import')
            imp.set('filename', temp_path)
            imp.set('type', format.upper())

            # Build geometry
            model.build()

            # Get list of domains/bodies
            bodies = []
            # This is simplified - actual implementation would query the geometry
            # for domain labels

            logger.info(f"Imported CAD geometry from {filename}")
            return bodies

        except Exception as e:
            raise COMSOLError(f"Failed to import CAD: {e}")
        finally:
            # Clean up temp file
            try:
                os.unlink(temp_path)
            except Exception:
                pass

    def run_study(self, model: Any, study_name: str = 'std1') -> None:
        """Execute a study in the model.

        Parameters
        ----------
        model : Model
            mph Model object
        study_name : str
            Name of the study to run

        Raises
        ------
        COMSOLError
            If study execution fails
        """
        try:
            logger.info(f"Running study: {study_name}")
            model.solve(study_name)
            logger.info(f"Study {study_name} completed")
        except Exception as e:
            raise COMSOLError(f"Study execution failed: {e}")

    def get_parameter(self, model: Any, name: str) -> Any:
        """Get a parameter value from the model.

        Parameters
        ----------
        model : Model
            mph Model object
        name : str
            Parameter name

        Returns
        -------
        value
            Parameter value
        """
        try:
            return model.parameter(name)
        except Exception:
            return None

    def set_parameter(self, model: Any, name: str, value: Any,
                      description: str = '') -> None:
        """Set a parameter in the model.

        Parameters
        ----------
        model : Model
            mph Model object
        name : str
            Parameter name
        value : any
            Parameter value
        description : str, optional
            Parameter description
        """
        try:
            model.parameter(name, value, description)
            logger.debug(f"Set parameter {name} = {value}")
        except Exception as e:
            raise COMSOLError(f"Failed to set parameter {name}: {e}")

    def evaluate(self, model: Any, expression: str,
                 dataset: str = None) -> Any:
        """Evaluate an expression in the model.

        Parameters
        ----------
        model : Model
            mph Model object
        expression : str
            Expression to evaluate (e.g., 'T', 'comp1.T')
        dataset : str, optional
            Dataset to evaluate on

        Returns
        -------
        result
            Evaluation result (typically numpy array)
        """
        try:
            if dataset:
                return model.evaluate(expression, dataset)
            return model.evaluate(expression)
        except Exception as e:
            raise COMSOLError(f"Evaluation failed for '{expression}': {e}")

    def export_data(self, model: Any, filename: str,
                    expression: str = 'T',
                    format: str = 'vtk') -> None:
        """Export solution data to file.

        Parameters
        ----------
        model : Model
            mph Model object
        filename : str
            Output filename
        expression : str
            Expression to export (default: temperature 'T')
        format : str
            Export format: 'vtk', 'txt', 'csv'
        """
        try:
            path = Path(filename)
            path.parent.mkdir(parents=True, exist_ok=True)

            # Create export node
            exp = model.java.result().export().create('data1', 'Data')
            exp.set('expr', expression)
            exp.set('filename', str(path))
            exp.run()

            logger.info(f"Exported data to: {filename}")
        except Exception as e:
            raise COMSOLError(f"Export failed: {e}")

    def get_names(self, model: Any, node_type: str) -> List[str]:
        """Get names of nodes of a specific type.

        Parameters
        ----------
        model : Model
            mph Model object
        node_type : str
            Type of node: 'physics', 'study', 'geometry', 'material'

        Returns
        -------
        list of str
            List of node names
        """
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
    """Mock COMSOL client for testing without actual COMSOL installation.

    Simulates COMSOL operations for development and testing purposes.
    """

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
        logger.info(f"Created mock COMSOL model: {name}")
        return model

    def load_model(self, filepath: str) -> dict:
        path = Path(filepath)
        if not path.exists():
            raise COMSOLError(f"Model file not found: {filepath}")
        # Return empty mock model
        return self.create_model(path.stem)

    def save_model(self, model: dict, filepath: str) -> None:
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        # In mock mode, just log the save
        logger.info(f"Mock saved model to: {filepath}")

    def import_cad(self, model: dict, cad_data: bytes, filename: str,
                   format: str = 'step') -> List[str]:
        # Return mock body names
        bodies = ['string_1', 'string_2', 'string_3', 'base_plate']
        model['geometries']['cad'] = {'bodies': bodies}
        logger.info(f"Mock imported CAD with {len(bodies)} bodies")
        return bodies

    def run_study(self, model: dict, study_name: str = 'std1') -> None:
        logger.info(f"Mock running study: {study_name}")
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
        import numpy as np
        # Return mock temperature data
        return np.linspace(1500, 100, 100)

    def export_data(self, model: dict, filename: str,
                    expression: str = 'T',
                    format: str = 'vtk') -> None:
        path = Path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Create empty file for mock
        path.touch()
        logger.info(f"Mock exported to: {filename}")
