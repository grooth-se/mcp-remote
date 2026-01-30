"""
Word report generator for CTOD E1290 test results.

Populates a Word template with test data, results, and crack surface photos.
"""

import re
from pathlib import Path
from typing import Dict, Any, Optional, List
from docx import Document
from docx.shared import Inches, Cm


class CTODReportGenerator:
    """
    Generate CTOD test reports from Word template.

    Uses placeholder syntax {{placeholder_name}} in template.
    """

    def __init__(self, template_path: Path):
        """
        Initialize report generator.

        Parameters
        ----------
        template_path : Path
            Path to Word template file
        """
        self.template_path = template_path
        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_path}")

    def generate_report(
        self,
        output_path: Path,
        data: Dict[str, Any],
        chart_path: Optional[Path] = None,
        logo_path: Optional[Path] = None,
        photo_paths: Optional[List[Path]] = None
    ) -> Path:
        """
        Generate report by populating template with data.

        Parameters
        ----------
        output_path : Path
            Path for output Word document
        data : Dict[str, Any]
            Dictionary of placeholder values
        chart_path : Path, optional
            Path to Force vs CMOD chart image
        logo_path : Path, optional
            Path to logo image to insert
        photo_paths : List[Path], optional
            List of paths to crack surface photos

        Returns
        -------
        Path
            Path to generated report
        """
        doc = Document(self.template_path)

        # Replace placeholders in page headers
        for section in doc.sections:
            header = section.header
            for paragraph in header.paragraphs:
                self._replace_in_paragraph(paragraph, data, chart_path, logo_path, photo_paths)
            for table in header.tables:
                for row in table.rows:
                    for cell in row.cells:
                        for paragraph in cell.paragraphs:
                            self._replace_in_paragraph(paragraph, data, chart_path, logo_path, photo_paths)

        # Replace placeholders in paragraphs
        for paragraph in doc.paragraphs:
            self._replace_in_paragraph(paragraph, data, chart_path, logo_path, photo_paths)

        # Replace placeholders in tables
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        self._replace_in_paragraph(paragraph, data, chart_path, logo_path, photo_paths)

        # Add disclaimer at the end of the document
        from docx.shared import Pt
        disclaimer_text = (
            "All work and services carried out by Durabler are subject to, and conducted in accordance with, "
            "Durabler standard terms and conditions, which are available at durabler.se. This document shall not "
            "be reproduced other than in full, except with prior written approval of the issuer. The results pertain "
            "only to the item(s) as sampled by the client unless otherwise indicated. Durabler a part of Subseatec S AB, "
            "Address: Durabler C/O Subseatec, Dalavägen 23, 68130 Kristinehamn, SWEDEN"
        )
        doc.add_paragraph()
        disclaimer = doc.add_paragraph()
        disclaimer_run = disclaimer.add_run(disclaimer_text)
        disclaimer_run.font.size = Pt(8)
        disclaimer_run.italic = True

        doc.save(output_path)
        return output_path

    def _replace_in_paragraph(
        self,
        paragraph,
        data: Dict[str, Any],
        chart_path: Optional[Path],
        logo_path: Optional[Path],
        photo_paths: Optional[List[Path]]
    ):
        """Replace placeholders in a paragraph."""
        full_text = paragraph.text

        # Handle logo placeholder
        if '{{logo}}' in full_text and logo_path and logo_path.exists():
            paragraph.clear()
            run = paragraph.add_run()
            run.add_picture(str(logo_path), height=Cm(1.5))
            return

        # Handle chart placeholder
        if '{{chart}}' in full_text and chart_path and chart_path.exists():
            paragraph.clear()
            run = paragraph.add_run()
            run.add_picture(str(chart_path), width=Inches(5.5))
            return

        # Handle photos placeholder
        if '{{photos}}' in full_text:
            paragraph.clear()
            if photo_paths:
                for i, photo_path in enumerate(photo_paths):
                    if photo_path and photo_path.exists():
                        run = paragraph.add_run()
                        # Add photo with half page width (3.5 inches)
                        run.add_picture(str(photo_path), width=Inches(3.5))
                        if i < len(photo_paths) - 1:
                            paragraph.add_run("\n")  # Newline between photos
            else:
                paragraph.add_run("No crack surface photos attached.")
            return

        # Find all placeholders
        placeholders = re.findall(r'\{\{([^}]+)\}\}', full_text)

        if not placeholders:
            return

        # Replace each placeholder
        for placeholder in placeholders:
            key = placeholder
            value = data.get(key, '')

            # Handle None values
            if value is None:
                value = ''

            # Format numeric values
            if isinstance(value, float):
                if abs(value) < 0.001:
                    value = f"{value:.4g}"
                elif abs(value) < 1:
                    value = f"{value:.4f}"
                else:
                    value = f"{value:.2f}"
            elif isinstance(value, int):
                value = str(value)

            full_text = full_text.replace(f'{{{{{placeholder}}}}}', str(value))

        # Update paragraph text while preserving formatting
        if paragraph.runs:
            first_run = paragraph.runs[0]
            font_name = first_run.font.name
            font_size = first_run.font.size
            bold = first_run.bold
            italic = first_run.italic

            paragraph.clear()
            new_run = paragraph.add_run(full_text)
            new_run.font.name = font_name
            new_run.font.size = font_size
            new_run.bold = bold
            new_run.italic = italic
        else:
            paragraph.text = full_text

    @staticmethod
    def prepare_report_data(
        test_info: Dict[str, str],
        specimen_data: Dict[str, Any],
        material_data: Dict[str, Any],
        results: Dict[str, Any],
        crack_measurements: Optional[List[float]] = None
    ) -> Dict[str, Any]:
        """
        Prepare data dictionary for report generation.

        Parameters
        ----------
        test_info : Dict[str, str]
            Test information (project, customer, etc.)
        specimen_data : Dict[str, Any]
            Specimen geometry data
        material_data : Dict[str, Any]
            Material properties
        results : Dict[str, Any]
            Analysis results with CTODResult and MeasuredValue objects
        crack_measurements : List[float], optional
            9-point crack length measurements

        Returns
        -------
        Dict[str, Any]
            Flattened dictionary ready for template
        """
        data = {}

        # Test information
        data['test_project'] = test_info.get('test_project', '')
        data['customer'] = test_info.get('customer', '')
        data['customer_order'] = test_info.get('customer_order', '')
        data['product_sn'] = test_info.get('product_sn', '')
        data['specimen_id'] = test_info.get('specimen_id', '')
        data['location_orientation'] = test_info.get('location_orientation', '')
        data['material'] = test_info.get('material', '')
        data['certificate_number'] = test_info.get('certificate_number', '')
        data['test_date'] = test_info.get('test_date', '')
        data['test_standard'] = 'ASTM E1290'
        data['test_equipment'] = 'MTS Landmark 500kN'
        data['test_temperature'] = test_info.get('temperature', '23')

        # Specimen geometry
        data['specimen_type'] = specimen_data.get('specimen_type', 'SE(B)')
        data['W'] = specimen_data.get('W', '')
        data['B'] = specimen_data.get('B', '')
        data['B_n'] = specimen_data.get('B_n', specimen_data.get('B', ''))
        data['a_0'] = specimen_data.get('a_0', '')
        data['S'] = specimen_data.get('S', '')
        data['a_f'] = specimen_data.get('a_f', '-')
        data['notch_type'] = specimen_data.get('notch_type', 'Fatigue pre-crack')
        data['side_grooves'] = 'Yes' if specimen_data.get('B_n') and specimen_data.get('B_n') < specimen_data.get('B', 0) else 'No'

        # Calculate a_0/W ratio and delta_a
        W = float(specimen_data.get('W', 1))
        a_0 = float(specimen_data.get('a_0', 0))
        data['a_W_ratio'] = f"{a_0 / W:.3f}" if W > 0 else '-'

        a_f = specimen_data.get('a_f')
        if a_f and a_f != '-':
            try:
                delta_a = float(a_f) - a_0
                data['delta_a'] = f"{delta_a:.3f}"
            except (ValueError, TypeError):
                data['delta_a'] = '-'
        else:
            data['delta_a'] = '-'

        # Material properties
        data['yield_strength'] = material_data.get('yield_strength', '')
        data['ultimate_strength'] = material_data.get('ultimate_strength', '')
        data['youngs_modulus'] = material_data.get('youngs_modulus', '')
        data['poissons_ratio'] = material_data.get('poissons_ratio', '0.3')

        # Helper to extract value and uncertainty from MeasuredValue objects
        def get_measured(obj, default_value='-', default_unc='-'):
            if obj and hasattr(obj, 'value'):
                return f"{obj.value:.4g}", f"±{obj.uncertainty:.4g}"
            return default_value, default_unc

        # Results from MeasuredValue objects
        P_max = results.get('P_max')
        if P_max:
            data['P_max_value'], data['P_max_uncertainty'] = get_measured(P_max)
        else:
            data['P_max_value'] = '-'
            data['P_max_uncertainty'] = '-'
        data['P_max_req'] = '-'  # Requirement placeholder

        CMOD_max = results.get('CMOD_max')
        if CMOD_max:
            data['CMOD_max_value'], data['CMOD_max_uncertainty'] = get_measured(CMOD_max)
        else:
            data['CMOD_max_value'] = '-'
            data['CMOD_max_uncertainty'] = '-'
        data['CMOD_max_req'] = '-'  # Requirement placeholder

        K_max = results.get('K_max')
        if K_max:
            data['K_max_value'], data['K_max_uncertainty'] = get_measured(K_max)
        else:
            data['K_max_value'] = '-'
            data['K_max_uncertainty'] = '-'
        data['K_max_req'] = '-'  # Requirement placeholder

        # CTOD results (CTODResult objects)
        ctod_type_reported = None

        for ctod_key, ctod_label in [('delta_c', 'δc'), ('delta_u', 'δu'), ('delta_m', 'δm')]:
            ctod_result = results.get(ctod_key)
            if ctod_result:
                val, unc = get_measured(ctod_result.ctod_value)
                data[f'{ctod_key}_value'] = val
                data[f'{ctod_key}_uncertainty'] = unc
                data[f'{ctod_key}_valid'] = 'VALID' if ctod_result.is_valid else 'INVALID'

                # Set reported type (prefer δc > δu > δm)
                if ctod_type_reported is None:
                    ctod_type_reported = ctod_label
            else:
                data[f'{ctod_key}_value'] = '-'
                data[f'{ctod_key}_uncertainty'] = '-'
                data[f'{ctod_key}_valid'] = '-'
            data[f'{ctod_key}_req'] = '-'  # Requirement placeholder for each CTOD type

        data['ctod_type'] = ctod_type_reported or '-'

        # Compliance
        compliance = results.get('compliance')
        if compliance:
            data['compliance'] = f"{compliance:.4f}"
        else:
            data['compliance'] = '-'

        # 9-point crack measurements
        if crack_measurements and len(crack_measurements) >= 9:
            for i, val in enumerate(crack_measurements[:9], 1):
                data[f'a{i}'] = f"{val:.2f}"
        else:
            for i in range(1, 10):
                data[f'a{i}'] = '-'

        # Validity
        is_valid = results.get('is_valid', False)
        data['validity_status'] = 'VALID' if is_valid else 'INVALID'
        validity_summary = results.get('validity_summary', '')
        if is_valid:
            data['validity_statement'] = 'The test meets all validity requirements of ASTM E1290.'
        else:
            data['validity_statement'] = f'The test does not meet all validity requirements. {validity_summary}'

        # Signatures (to be filled manually)
        data['tested_by'] = ''
        data['tested_date'] = ''
        data['reviewed_by'] = ''
        data['reviewed_date'] = ''
        data['approved_by'] = ''
        data['approved_date'] = ''

        return data
