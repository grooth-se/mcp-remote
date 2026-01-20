"""
Test Data Database Module.

Provides database storage for all test data, results, plots, and photos.
Enables full report regeneration from stored data.

Database: data/test_data.db (SQLite)
"""

import sqlite3
import json
import zlib
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from dataclasses import asdict
import numpy as np

# Database file location
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATABASE_PATH = PROJECT_ROOT / "data" / "test_data.db"


class TestDataDatabase:
    """
    Database interface for storing and retrieving test data.

    Supports all test types: Tensile, FCGR, KIC, CTOD, Sonic, Vickers.
    Stores raw data arrays, calculated results, plots, and photos.
    """

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize database connection.

        Parameters
        ----------
        db_path : Path, optional
            Path to database file. Defaults to data/test_data.db
        """
        self.db_path = db_path or DATABASE_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_database(self):
        """Create database tables if they don't exist."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Table 1: test_records (main table)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS test_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                certificate_number TEXT NOT NULL UNIQUE,
                test_type TEXT NOT NULL,
                test_standard TEXT,

                -- Test Information (all searchable)
                test_project TEXT,
                project_name TEXT,
                customer TEXT,
                customer_order TEXT,
                product_sn TEXT,
                specimen_id TEXT,
                location_orientation TEXT,
                material TEXT,
                test_date TEXT,
                temperature TEXT,
                operator TEXT,
                test_equipment TEXT,
                comments TEXT,

                -- Status
                status TEXT DEFAULT 'DRAFT',
                is_valid INTEGER DEFAULT 1,
                validity_notes TEXT,

                -- Timestamps
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

                -- Link to certificate register
                certificate_id INTEGER
            )
        """)

        # Table 2: specimen_geometry
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS specimen_geometry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_id INTEGER NOT NULL,
                specimen_type TEXT,

                -- Common dimensions (mm)
                W REAL,
                B REAL,
                B_n REAL,
                a_0 REAL,
                S REAL,

                -- Tensile specific
                diameter REAL,
                diameter_std REAL,
                width REAL,
                width_std REAL,
                thickness REAL,
                thickness_std REAL,
                gauge_length REAL,
                parallel_length REAL,
                final_diameter REAL,
                final_gauge_length REAL,
                cross_section_area REAL,

                -- Sonic specific
                length REAL,
                mass REAL,
                side_length REAL,

                -- Computed values
                a_W_ratio REAL,
                ligament REAL,

                FOREIGN KEY (test_id) REFERENCES test_records(id) ON DELETE CASCADE
            )
        """)

        # Table 3: material_properties
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS material_properties (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_id INTEGER NOT NULL,

                yield_strength REAL,
                ultimate_strength REAL,
                youngs_modulus REAL,
                poissons_ratio REAL DEFAULT 0.3,

                FOREIGN KEY (test_id) REFERENCES test_records(id) ON DELETE CASCADE
            )
        """)

        # Table 4: raw_data
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS raw_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_id INTEGER NOT NULL,
                data_type TEXT NOT NULL,

                -- Common arrays (compressed JSON BLOB)
                time_data BLOB,
                force_data BLOB,
                displacement_data BLOB,
                extension_data BLOB,
                cycle_data BLOB,

                -- Sonic velocities
                longitudinal_velocities TEXT,
                shear_velocities TEXT,

                -- Vickers readings
                hardness_readings TEXT,
                load_level TEXT,

                -- Metadata
                source_file TEXT,
                num_points INTEGER,

                FOREIGN KEY (test_id) REFERENCES test_records(id) ON DELETE CASCADE
            )
        """)

        # Table 5: test_results
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS test_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_id INTEGER NOT NULL,
                parameter_name TEXT NOT NULL,

                value REAL,
                uncertainty REAL,
                unit TEXT,
                coverage_factor REAL DEFAULT 2.0,
                extra_data TEXT,
                is_valid INTEGER DEFAULT 1,

                FOREIGN KEY (test_id) REFERENCES test_records(id) ON DELETE CASCADE
            )
        """)

        # Table 6: crack_measurements
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS crack_measurements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_id INTEGER NOT NULL,
                measurement_type TEXT NOT NULL,

                measurements TEXT,
                average_value REAL,

                FOREIGN KEY (test_id) REFERENCES test_records(id) ON DELETE CASCADE
            )
        """)

        # Table 7: test_blobs
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS test_blobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_id INTEGER NOT NULL,
                blob_type TEXT NOT NULL,
                description TEXT,

                data BLOB NOT NULL,
                mime_type TEXT,
                filename TEXT,

                created_at TEXT DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (test_id) REFERENCES test_records(id) ON DELETE CASCADE
            )
        """)

        # Table 8: fcgr_data_points
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fcgr_data_points (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_id INTEGER NOT NULL,

                cycle_count INTEGER,
                crack_length REAL,
                delta_K REAL,
                da_dN REAL,
                P_max REAL,
                P_min REAL,
                compliance REAL,

                is_valid INTEGER DEFAULT 1,
                is_outlier INTEGER DEFAULT 0,

                FOREIGN KEY (test_id) REFERENCES test_records(id) ON DELETE CASCADE
            )
        """)

        # Table 9: paris_law_results
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS paris_law_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_id INTEGER NOT NULL,
                fit_type TEXT,

                C REAL,
                m REAL,
                r_squared REAL,
                n_points INTEGER,

                delta_K_min REAL,
                delta_K_max REAL,
                da_dN_min REAL,
                da_dN_max REAL,

                std_error_C REAL,
                std_error_m REAL,

                FOREIGN KEY (test_id) REFERENCES test_records(id) ON DELETE CASCADE
            )
        """)

        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_test_cert_number ON test_records(certificate_number)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_test_type ON test_records(test_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_test_customer ON test_records(customer)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_test_project ON test_records(test_project)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_test_material ON test_records(material)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_test_specimen ON test_records(specimen_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_test_date ON test_records(test_date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_results_test ON test_results(test_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_results_param ON test_results(parameter_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_blobs_test ON test_blobs(test_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_blobs_type ON test_blobs(blob_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_fcgr_test ON fcgr_data_points(test_id)")

        conn.commit()
        conn.close()

    # =========================================================================
    # Compression utilities
    # =========================================================================

    @staticmethod
    def compress_array(arr: np.ndarray) -> bytes:
        """Compress numpy array to bytes."""
        if arr is None:
            return None
        data_json = json.dumps(arr.tolist())
        return zlib.compress(data_json.encode('utf-8'))

    @staticmethod
    def decompress_array(data: bytes) -> Optional[np.ndarray]:
        """Decompress bytes to numpy array."""
        if data is None:
            return None
        decompressed = zlib.decompress(data)
        return np.array(json.loads(decompressed.decode('utf-8')))

    # =========================================================================
    # Test Records CRUD
    # =========================================================================

    def save_test_record(self, record: Dict[str, Any]) -> int:
        """
        Save or update a test record.

        Parameters
        ----------
        record : Dict[str, Any]
            Test record data with certificate_number as key

        Returns
        -------
        int
            Record ID
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # Check if record exists
        cursor.execute(
            "SELECT id FROM test_records WHERE certificate_number = ?",
            (record['certificate_number'],)
        )
        existing = cursor.fetchone()

        now = datetime.now().isoformat()

        if existing:
            # Update existing record
            test_id = existing['id']
            cursor.execute("""
                UPDATE test_records SET
                    test_type = ?,
                    test_standard = ?,
                    test_project = ?,
                    project_name = ?,
                    customer = ?,
                    customer_order = ?,
                    product_sn = ?,
                    specimen_id = ?,
                    location_orientation = ?,
                    material = ?,
                    test_date = ?,
                    temperature = ?,
                    operator = ?,
                    test_equipment = ?,
                    comments = ?,
                    status = ?,
                    is_valid = ?,
                    validity_notes = ?,
                    updated_at = ?,
                    certificate_id = ?
                WHERE id = ?
            """, (
                record.get('test_type'),
                record.get('test_standard'),
                record.get('test_project'),
                record.get('project_name'),
                record.get('customer'),
                record.get('customer_order'),
                record.get('product_sn'),
                record.get('specimen_id'),
                record.get('location_orientation'),
                record.get('material'),
                record.get('test_date'),
                record.get('temperature'),
                record.get('operator'),
                record.get('test_equipment'),
                record.get('comments'),
                record.get('status', 'DRAFT'),
                1 if record.get('is_valid', True) else 0,
                json.dumps(record.get('validity_notes', [])),
                now,
                record.get('certificate_id'),
                test_id
            ))
        else:
            # Insert new record
            cursor.execute("""
                INSERT INTO test_records (
                    certificate_number, test_type, test_standard,
                    test_project, project_name, customer, customer_order,
                    product_sn, specimen_id, location_orientation, material,
                    test_date, temperature, operator, test_equipment, comments,
                    status, is_valid, validity_notes, created_at, updated_at,
                    certificate_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record['certificate_number'],
                record.get('test_type'),
                record.get('test_standard'),
                record.get('test_project'),
                record.get('project_name'),
                record.get('customer'),
                record.get('customer_order'),
                record.get('product_sn'),
                record.get('specimen_id'),
                record.get('location_orientation'),
                record.get('material'),
                record.get('test_date'),
                record.get('temperature'),
                record.get('operator'),
                record.get('test_equipment'),
                record.get('comments'),
                record.get('status', 'DRAFT'),
                1 if record.get('is_valid', True) else 0,
                json.dumps(record.get('validity_notes', [])),
                now,
                now,
                record.get('certificate_id')
            ))
            test_id = cursor.lastrowid

        conn.commit()
        conn.close()
        return test_id

    def get_test_record(self, certificate_number: str) -> Optional[Dict[str, Any]]:
        """Get test record by certificate number."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM test_records WHERE certificate_number = ?",
            (certificate_number,)
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            record = dict(row)
            if record.get('validity_notes'):
                record['validity_notes'] = json.loads(record['validity_notes'])
            record['is_valid'] = bool(record.get('is_valid', 1))
            return record
        return None

    def get_test_record_by_id(self, test_id: int) -> Optional[Dict[str, Any]]:
        """Get test record by ID."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM test_records WHERE id = ?", (test_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            record = dict(row)
            if record.get('validity_notes'):
                record['validity_notes'] = json.loads(record['validity_notes'])
            record['is_valid'] = bool(record.get('is_valid', 1))
            return record
        return None

    def delete_test_record(self, certificate_number: str) -> bool:
        """Delete test record and all related data."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "DELETE FROM test_records WHERE certificate_number = ?",
            (certificate_number,)
        )
        deleted = cursor.rowcount > 0

        conn.commit()
        conn.close()
        return deleted

    # =========================================================================
    # Specimen Geometry
    # =========================================================================

    def save_specimen_geometry(self, test_id: int, geometry: Dict[str, Any]) -> int:
        """Save specimen geometry for a test."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Delete existing geometry
        cursor.execute("DELETE FROM specimen_geometry WHERE test_id = ?", (test_id,))

        cursor.execute("""
            INSERT INTO specimen_geometry (
                test_id, specimen_type,
                W, B, B_n, a_0, S,
                diameter, diameter_std, width, width_std, thickness, thickness_std,
                gauge_length, parallel_length, final_diameter, final_gauge_length,
                cross_section_area, length, mass, side_length,
                a_W_ratio, ligament
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            test_id,
            geometry.get('specimen_type'),
            geometry.get('W'),
            geometry.get('B'),
            geometry.get('B_n'),
            geometry.get('a_0'),
            geometry.get('S'),
            geometry.get('diameter'),
            geometry.get('diameter_std'),
            geometry.get('width'),
            geometry.get('width_std'),
            geometry.get('thickness'),
            geometry.get('thickness_std'),
            geometry.get('gauge_length'),
            geometry.get('parallel_length'),
            geometry.get('final_diameter'),
            geometry.get('final_gauge_length'),
            geometry.get('cross_section_area'),
            geometry.get('length'),
            geometry.get('mass'),
            geometry.get('side_length'),
            geometry.get('a_W_ratio'),
            geometry.get('ligament')
        ))

        geometry_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return geometry_id

    def get_specimen_geometry(self, test_id: int) -> Optional[Dict[str, Any]]:
        """Get specimen geometry for a test."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM specimen_geometry WHERE test_id = ?",
            (test_id,)
        )
        row = cursor.fetchone()
        conn.close()

        return dict(row) if row else None

    # =========================================================================
    # Material Properties
    # =========================================================================

    def save_material_properties(self, test_id: int, material: Dict[str, Any]) -> int:
        """Save material properties for a test."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Delete existing
        cursor.execute("DELETE FROM material_properties WHERE test_id = ?", (test_id,))

        cursor.execute("""
            INSERT INTO material_properties (
                test_id, yield_strength, ultimate_strength,
                youngs_modulus, poissons_ratio
            ) VALUES (?, ?, ?, ?, ?)
        """, (
            test_id,
            material.get('yield_strength'),
            material.get('ultimate_strength'),
            material.get('youngs_modulus'),
            material.get('poissons_ratio', 0.3)
        ))

        material_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return material_id

    def get_material_properties(self, test_id: int) -> Optional[Dict[str, Any]]:
        """Get material properties for a test."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM material_properties WHERE test_id = ?",
            (test_id,)
        )
        row = cursor.fetchone()
        conn.close()

        return dict(row) if row else None

    # =========================================================================
    # Raw Data
    # =========================================================================

    def save_raw_data(self, test_id: int, data_type: str, data: Dict[str, Any]) -> int:
        """
        Save raw test data arrays.

        Parameters
        ----------
        test_id : int
            Test record ID
        data_type : str
            Type of data: 'main', 'precrack', 'crack_check', 'velocities'
        data : Dict[str, Any]
            Raw data including arrays and metadata
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # Delete existing data of this type
        cursor.execute(
            "DELETE FROM raw_data WHERE test_id = ? AND data_type = ?",
            (test_id, data_type)
        )

        # Compress arrays
        time_data = self.compress_array(data.get('time')) if data.get('time') is not None else None
        force_data = self.compress_array(data.get('force')) if data.get('force') is not None else None
        displacement_data = self.compress_array(data.get('displacement')) if data.get('displacement') is not None else None
        extension_data = self.compress_array(data.get('extension')) if data.get('extension') is not None else None
        cycle_data = self.compress_array(data.get('cycles')) if data.get('cycles') is not None else None

        cursor.execute("""
            INSERT INTO raw_data (
                test_id, data_type,
                time_data, force_data, displacement_data, extension_data, cycle_data,
                longitudinal_velocities, shear_velocities,
                hardness_readings, load_level,
                source_file, num_points
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            test_id,
            data_type,
            time_data,
            force_data,
            displacement_data,
            extension_data,
            cycle_data,
            json.dumps(data.get('longitudinal_velocities')) if data.get('longitudinal_velocities') else None,
            json.dumps(data.get('shear_velocities')) if data.get('shear_velocities') else None,
            json.dumps(data.get('hardness_readings')) if data.get('hardness_readings') else None,
            data.get('load_level'),
            data.get('source_file'),
            data.get('num_points')
        ))

        raw_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return raw_id

    def get_raw_data(self, test_id: int, data_type: str = 'main') -> Optional[Dict[str, Any]]:
        """Get raw test data arrays."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM raw_data WHERE test_id = ? AND data_type = ?",
            (test_id, data_type)
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        data = dict(row)

        # Decompress arrays
        data['time'] = self.decompress_array(data.get('time_data'))
        data['force'] = self.decompress_array(data.get('force_data'))
        data['displacement'] = self.decompress_array(data.get('displacement_data'))
        data['extension'] = self.decompress_array(data.get('extension_data'))
        data['cycles'] = self.decompress_array(data.get('cycle_data'))

        # Parse JSON fields
        if data.get('longitudinal_velocities'):
            data['longitudinal_velocities'] = json.loads(data['longitudinal_velocities'])
        if data.get('shear_velocities'):
            data['shear_velocities'] = json.loads(data['shear_velocities'])
        if data.get('hardness_readings'):
            data['hardness_readings'] = json.loads(data['hardness_readings'])

        return data

    # =========================================================================
    # Test Results
    # =========================================================================

    def save_test_result(self, test_id: int, parameter_name: str,
                         value: float, uncertainty: float = None,
                         unit: str = None, extra_data: Dict = None,
                         is_valid: bool = True) -> int:
        """Save a single test result."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Delete existing result for this parameter
        cursor.execute(
            "DELETE FROM test_results WHERE test_id = ? AND parameter_name = ?",
            (test_id, parameter_name)
        )

        cursor.execute("""
            INSERT INTO test_results (
                test_id, parameter_name, value, uncertainty, unit,
                coverage_factor, extra_data, is_valid
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            test_id,
            parameter_name,
            value,
            uncertainty,
            unit,
            2.0,
            json.dumps(extra_data) if extra_data else None,
            1 if is_valid else 0
        ))

        result_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return result_id

    def save_test_results_batch(self, test_id: int, results: List[Dict[str, Any]]) -> int:
        """
        Save multiple test results at once.

        Parameters
        ----------
        test_id : int
            Test record ID
        results : List[Dict]
            List of result dicts with keys: parameter_name, value, uncertainty, unit
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # Delete all existing results for this test
        cursor.execute("DELETE FROM test_results WHERE test_id = ?", (test_id,))

        for result in results:
            cursor.execute("""
                INSERT INTO test_results (
                    test_id, parameter_name, value, uncertainty, unit,
                    coverage_factor, extra_data, is_valid
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                test_id,
                result.get('parameter_name'),
                result.get('value'),
                result.get('uncertainty'),
                result.get('unit'),
                result.get('coverage_factor', 2.0),
                json.dumps(result.get('extra_data')) if result.get('extra_data') else None,
                1 if result.get('is_valid', True) else 0
            ))

        conn.commit()
        conn.close()
        return len(results)

    def get_test_results(self, test_id: int) -> List[Dict[str, Any]]:
        """Get all results for a test."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM test_results WHERE test_id = ? ORDER BY id",
            (test_id,)
        )
        rows = cursor.fetchall()
        conn.close()

        results = []
        for row in rows:
            result = dict(row)
            if result.get('extra_data'):
                result['extra_data'] = json.loads(result['extra_data'])
            result['is_valid'] = bool(result.get('is_valid', 1))
            results.append(result)

        return results

    # =========================================================================
    # Crack Measurements
    # =========================================================================

    def save_crack_measurements(self, test_id: int, measurement_type: str,
                                 measurements: List[float], average: float = None) -> int:
        """Save crack measurements."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Delete existing
        cursor.execute(
            "DELETE FROM crack_measurements WHERE test_id = ? AND measurement_type = ?",
            (test_id, measurement_type)
        )

        cursor.execute("""
            INSERT INTO crack_measurements (
                test_id, measurement_type, measurements, average_value
            ) VALUES (?, ?, ?, ?)
        """, (
            test_id,
            measurement_type,
            json.dumps(measurements),
            average
        ))

        meas_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return meas_id

    def get_crack_measurements(self, test_id: int, measurement_type: str = None) -> List[Dict[str, Any]]:
        """Get crack measurements for a test."""
        conn = self._get_connection()
        cursor = conn.cursor()

        if measurement_type:
            cursor.execute(
                "SELECT * FROM crack_measurements WHERE test_id = ? AND measurement_type = ?",
                (test_id, measurement_type)
            )
        else:
            cursor.execute(
                "SELECT * FROM crack_measurements WHERE test_id = ?",
                (test_id,)
            )

        rows = cursor.fetchall()
        conn.close()

        results = []
        for row in rows:
            result = dict(row)
            if result.get('measurements'):
                result['measurements'] = json.loads(result['measurements'])
            results.append(result)

        return results

    # =========================================================================
    # Test Blobs (Plots and Photos)
    # =========================================================================

    def save_blob(self, test_id: int, blob_type: str, data: bytes,
                  description: str = None, mime_type: str = None,
                  filename: str = None) -> int:
        """Save binary data (plot or photo)."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO test_blobs (
                test_id, blob_type, description, data, mime_type, filename
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            test_id,
            blob_type,
            description,
            data,
            mime_type,
            filename
        ))

        blob_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return blob_id

    def save_plot(self, test_id: int, plot_data: bytes,
                  description: str = 'Plot') -> int:
        """Save plot image."""
        return self.save_blob(
            test_id, 'plot', plot_data,
            description=description,
            mime_type='image/png'
        )

    def save_photo(self, test_id: int, photo_path: Path,
                   description: str = 'Photo') -> int:
        """Save photo from file path."""
        with open(photo_path, 'rb') as f:
            data = f.read()

        mime_type = 'image/jpeg'
        if photo_path.suffix.lower() == '.png':
            mime_type = 'image/png'

        return self.save_blob(
            test_id, 'photo', data,
            description=description,
            mime_type=mime_type,
            filename=photo_path.name
        )

    def get_blobs(self, test_id: int, blob_type: str = None) -> List[Dict[str, Any]]:
        """Get blobs for a test."""
        conn = self._get_connection()
        cursor = conn.cursor()

        if blob_type:
            cursor.execute(
                "SELECT * FROM test_blobs WHERE test_id = ? AND blob_type = ?",
                (test_id, blob_type)
            )
        else:
            cursor.execute(
                "SELECT * FROM test_blobs WHERE test_id = ?",
                (test_id,)
            )

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_plot(self, test_id: int) -> Optional[bytes]:
        """Get main plot for a test."""
        blobs = self.get_blobs(test_id, 'plot')
        if blobs:
            return blobs[0].get('data')
        return None

    def get_photos(self, test_id: int) -> List[Dict[str, Any]]:
        """Get all photos for a test."""
        return self.get_blobs(test_id, 'photo')

    def delete_blobs(self, test_id: int, blob_type: str = None):
        """Delete blobs for a test."""
        conn = self._get_connection()
        cursor = conn.cursor()

        if blob_type:
            cursor.execute(
                "DELETE FROM test_blobs WHERE test_id = ? AND blob_type = ?",
                (test_id, blob_type)
            )
        else:
            cursor.execute(
                "DELETE FROM test_blobs WHERE test_id = ?",
                (test_id,)
            )

        conn.commit()
        conn.close()

    # =========================================================================
    # FCGR-specific methods
    # =========================================================================

    def save_fcgr_data_points(self, test_id: int, data_points: List[Dict[str, Any]]) -> int:
        """Save FCGR per-cycle data points."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Delete existing
        cursor.execute("DELETE FROM fcgr_data_points WHERE test_id = ?", (test_id,))

        for dp in data_points:
            cursor.execute("""
                INSERT INTO fcgr_data_points (
                    test_id, cycle_count, crack_length, delta_K, da_dN,
                    P_max, P_min, compliance, is_valid, is_outlier
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                test_id,
                dp.get('cycle_count'),
                dp.get('crack_length'),
                dp.get('delta_K'),
                dp.get('da_dN'),
                dp.get('P_max'),
                dp.get('P_min'),
                dp.get('compliance'),
                1 if dp.get('is_valid', True) else 0,
                1 if dp.get('is_outlier', False) else 0
            ))

        conn.commit()
        conn.close()
        return len(data_points)

    def get_fcgr_data_points(self, test_id: int) -> List[Dict[str, Any]]:
        """Get FCGR data points for a test."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM fcgr_data_points WHERE test_id = ? ORDER BY cycle_count",
            (test_id,)
        )
        rows = cursor.fetchall()
        conn.close()

        results = []
        for row in rows:
            dp = dict(row)
            dp['is_valid'] = bool(dp.get('is_valid', 1))
            dp['is_outlier'] = bool(dp.get('is_outlier', 0))
            results.append(dp)

        return results

    def save_paris_law_result(self, test_id: int, fit_type: str,
                               paris_result: Dict[str, Any]) -> int:
        """Save Paris law regression result."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Delete existing of this fit type
        cursor.execute(
            "DELETE FROM paris_law_results WHERE test_id = ? AND fit_type = ?",
            (test_id, fit_type)
        )

        cursor.execute("""
            INSERT INTO paris_law_results (
                test_id, fit_type, C, m, r_squared, n_points,
                delta_K_min, delta_K_max, da_dN_min, da_dN_max,
                std_error_C, std_error_m
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            test_id,
            fit_type,
            paris_result.get('C'),
            paris_result.get('m'),
            paris_result.get('r_squared'),
            paris_result.get('n_points'),
            paris_result.get('delta_K_min'),
            paris_result.get('delta_K_max'),
            paris_result.get('da_dN_min'),
            paris_result.get('da_dN_max'),
            paris_result.get('std_error_C'),
            paris_result.get('std_error_m')
        ))

        result_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return result_id

    def get_paris_law_results(self, test_id: int) -> List[Dict[str, Any]]:
        """Get Paris law results for a test."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM paris_law_results WHERE test_id = ?",
            (test_id,)
        )
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    # =========================================================================
    # Search and Query
    # =========================================================================

    def search_tests(self, search_term: str, test_type: str = None,
                     limit: int = 100) -> List[Dict[str, Any]]:
        """
        Search tests by any test information field.

        Parameters
        ----------
        search_term : str
            Search term (partial match)
        test_type : str, optional
            Filter by test type (TENSILE, FCGR, etc.)
        limit : int
            Maximum results to return

        Returns
        -------
        List[Dict]
            Matching test records
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        search_pattern = f"%{search_term}%"

        if test_type:
            cursor.execute("""
                SELECT * FROM test_records
                WHERE test_type = ? AND (
                    certificate_number LIKE ?
                    OR test_project LIKE ?
                    OR customer LIKE ?
                    OR customer_order LIKE ?
                    OR product_sn LIKE ?
                    OR specimen_id LIKE ?
                    OR material LIKE ?
                    OR location_orientation LIKE ?
                    OR operator LIKE ?
                    OR comments LIKE ?
                )
                ORDER BY test_date DESC, certificate_number DESC
                LIMIT ?
            """, (test_type,) + (search_pattern,) * 10 + (limit,))
        else:
            cursor.execute("""
                SELECT * FROM test_records
                WHERE certificate_number LIKE ?
                   OR test_project LIKE ?
                   OR customer LIKE ?
                   OR customer_order LIKE ?
                   OR product_sn LIKE ?
                   OR specimen_id LIKE ?
                   OR material LIKE ?
                   OR location_orientation LIKE ?
                   OR operator LIKE ?
                   OR comments LIKE ?
                ORDER BY test_date DESC, certificate_number DESC
                LIMIT ?
            """, (search_pattern,) * 10 + (limit,))

        rows = cursor.fetchall()
        conn.close()

        results = []
        for row in rows:
            record = dict(row)
            if record.get('validity_notes'):
                record['validity_notes'] = json.loads(record['validity_notes'])
            record['is_valid'] = bool(record.get('is_valid', 1))
            results.append(record)

        return results

    def get_all_tests(self, test_type: str = None, limit: int = 100,
                      offset: int = 0) -> List[Dict[str, Any]]:
        """Get all tests, optionally filtered by type."""
        conn = self._get_connection()
        cursor = conn.cursor()

        if test_type:
            cursor.execute("""
                SELECT * FROM test_records
                WHERE test_type = ?
                ORDER BY test_date DESC, certificate_number DESC
                LIMIT ? OFFSET ?
            """, (test_type, limit, offset))
        else:
            cursor.execute("""
                SELECT * FROM test_records
                ORDER BY test_date DESC, certificate_number DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))

        rows = cursor.fetchall()
        conn.close()

        results = []
        for row in rows:
            record = dict(row)
            if record.get('validity_notes'):
                record['validity_notes'] = json.loads(record['validity_notes'])
            record['is_valid'] = bool(record.get('is_valid', 1))
            results.append(record)

        return results

    def get_certificate_numbers_list(self, test_type: str = None) -> List[str]:
        """Get list of certificate numbers for dropdown."""
        conn = self._get_connection()
        cursor = conn.cursor()

        if test_type:
            cursor.execute("""
                SELECT certificate_number FROM test_records
                WHERE test_type = ?
                ORDER BY certificate_number DESC
            """, (test_type,))
        else:
            cursor.execute("""
                SELECT certificate_number FROM test_records
                ORDER BY certificate_number DESC
            """)

        rows = cursor.fetchall()
        conn.close()

        return [row['certificate_number'] for row in rows]

    def get_record_count(self, test_type: str = None) -> int:
        """Get total number of test records."""
        conn = self._get_connection()
        cursor = conn.cursor()

        if test_type:
            cursor.execute(
                "SELECT COUNT(*) as count FROM test_records WHERE test_type = ?",
                (test_type,)
            )
        else:
            cursor.execute("SELECT COUNT(*) as count FROM test_records")

        row = cursor.fetchone()
        conn.close()

        return row['count'] if row else 0

    def test_exists(self, certificate_number: str) -> bool:
        """Check if a test with this certificate number exists."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT 1 FROM test_records WHERE certificate_number = ?",
            (certificate_number,)
        )
        exists = cursor.fetchone() is not None

        conn.close()
        return exists
