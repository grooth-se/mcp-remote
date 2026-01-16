"""
Script to create the Sonic Resonance (E1875) report Word template.
"""

from pathlib import Path
from docx import Document
from docx.shared import Inches, Cm, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


def set_cell_shading(cell, color):
    """Set cell background color."""
    shading = OxmlElement('w:shd')
    shading.set(qn('w:fill'), color)
    cell._tc.get_or_add_tcPr().append(shading)


def set_table_column_widths(table, widths_inches):
    """Set column widths for a table."""
    tbl = table._tbl
    tblPr = tbl.tblPr if tbl.tblPr is not None else OxmlElement('w:tblPr')
    tblLayout = OxmlElement('w:tblLayout')
    tblLayout.set(qn('w:type'), 'fixed')
    tblPr.append(tblLayout)
    if tbl.tblPr is None:
        tbl.insert(0, tblPr)

    for row in table.rows:
        for idx, width in enumerate(widths_inches):
            if idx < len(row.cells):
                cell = row.cells[idx]
                tc = cell._tc
                tcPr = tc.get_or_add_tcPr()
                tcW = OxmlElement('w:tcW')
                tcW.set(qn('w:w'), str(int(width * 1440)))
                tcW.set(qn('w:type'), 'dxa')
                existing = tcPr.find(qn('w:tcW'))
                if existing is not None:
                    tcPr.remove(existing)
                tcPr.insert(0, tcW)


def create_template():
    doc = Document()

    # Set narrow margins
    for section in doc.sections:
        section.top_margin = Cm(1.5)
        section.bottom_margin = Cm(1.5)
        section.left_margin = Cm(2)
        section.right_margin = Cm(2)

    # Header with logo
    header_table = doc.add_table(rows=1, cols=2)
    header_table.autofit = False
    set_table_column_widths(header_table, [2.0, 5.0])

    logo_cell = header_table.rows[0].cells[0]
    logo_cell.text = ""
    logo_para = logo_cell.paragraphs[0]
    logo_para.add_run("{{logo}}")
    logo_para.alignment = WD_ALIGN_PARAGRAPH.LEFT

    title_cell = header_table.rows[0].cells[1]
    title_cell.text = ""
    title_para = title_cell.paragraphs[0]
    title_run = title_para.add_run("SONIC RESONANCE TEST REPORT")
    title_run.bold = True
    title_run.font.size = Pt(16)
    title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER

    std_para = title_cell.add_paragraph()
    std_run = std_para.add_run("Modified ASTM E1875 - Ultrasonic Method")
    std_run.font.size = Pt(11)
    std_para.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_paragraph()

    # Test Information Table
    info_heading = doc.add_paragraph()
    info_heading.add_run("Test Information").bold = True

    info_table = doc.add_table(rows=6, cols=4)
    info_table.style = 'Table Grid'

    info_data = [
        ("Test Project:", "{{test_project}}", "Certificate No:", "{{certificate_number}}"),
        ("Customer:", "{{customer}}", "Test Date:", "{{test_date}}"),
        ("Customer Order:", "{{customer_order}}", "Test Standard:", "{{test_standard}}"),
        ("Product/S/N:", "{{product_sn}}", "Specimen ID:", "{{specimen_id}}"),
        ("Material:", "{{material}}", "Test Temperature:", "{{temperature}} °C"),
        ("Location/Orient.:", "{{location_orientation}}", "Test Equipment:", "{{test_equipment}}"),
    ]

    for i, row_data in enumerate(info_data):
        row = info_table.rows[i]
        for j, text in enumerate(row_data):
            cell = row.cells[j]
            cell.text = text
            if j % 2 == 0:
                cell.paragraphs[0].runs[0].bold = True
                set_cell_shading(cell, 'E8E8E8')

    doc.add_paragraph()

    # Specimen Geometry Table
    dim_heading = doc.add_paragraph()
    dim_heading.add_run("Specimen Geometry").bold = True

    dim_table = doc.add_table(rows=2, cols=6)
    dim_table.style = 'Table Grid'

    dim_data = [
        ("Type:", "{{specimen_type}}", "Diameter (mm):", "{{diameter}}", "Side (mm):", "{{side_length}}"),
        ("Length (mm):", "{{length}}", "Mass (g):", "{{mass}}", "Density (kg/m³):", "{{density}}"),
    ]

    for i, row_data in enumerate(dim_data):
        row = dim_table.rows[i]
        for j, text in enumerate(row_data):
            cell = row.cells[j]
            cell.text = text
            if j % 2 == 0 and text:
                cell.paragraphs[0].runs[0].bold = True
                set_cell_shading(cell, 'E8E8E8')

    doc.add_paragraph()

    # Velocity Measurements Table
    vel_heading = doc.add_paragraph()
    vel_heading.add_run("Ultrasonic Velocity Measurements").bold = True

    vel_table = doc.add_table(rows=3, cols=5)
    vel_table.style = 'Table Grid'

    # Header row
    vel_headers = ["Wave Type", "V₁ (m/s)", "V₂ (m/s)", "V₃ (m/s)", "Average (m/s)"]
    for i, header in enumerate(vel_headers):
        cell = vel_table.rows[0].cells[i]
        cell.text = header
        cell.paragraphs[0].runs[0].bold = True
        set_cell_shading(cell, 'D0D0D0')
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Longitudinal row
    long_data = ["Longitudinal (Vl)", "{{vl1}}", "{{vl2}}", "{{vl3}}", "{{vl_avg}}"]
    for i, text in enumerate(long_data):
        cell = vel_table.rows[1].cells[i]
        cell.text = text
        if i == 0:
            set_cell_shading(cell, 'F0F0F0')

    # Shear row
    shear_data = ["Shear (Vs)", "{{vs1}}", "{{vs2}}", "{{vs3}}", "{{vs_avg}}"]
    for i, text in enumerate(shear_data):
        cell = vel_table.rows[2].cells[i]
        cell.text = text
        if i == 0:
            set_cell_shading(cell, 'F0F0F0')

    doc.add_paragraph()

    # Results Table
    results_heading = doc.add_paragraph()
    results_heading.add_run("Test Results").bold = True

    results_table = doc.add_table(rows=7, cols=4)
    results_table.style = 'Table Grid'

    # Header row
    res_headers = ["Parameter", "Value", "U (k=2)", "Unit"]
    for i, header in enumerate(res_headers):
        cell = results_table.rows[0].cells[i]
        cell.text = header
        cell.paragraphs[0].runs[0].bold = True
        set_cell_shading(cell, 'D0D0D0')
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Results rows
    results_data = [
        ("Poisson's Ratio (ν)", "{{poissons_ratio}}", "{{poissons_ratio_unc}}", "-"),
        ("Shear Modulus (G)", "{{shear_modulus}}", "{{shear_modulus_unc}}", "GPa"),
        ("Young's Modulus (E)", "{{youngs_modulus}}", "{{youngs_modulus_unc}}", "GPa"),
        ("Flexural Frequency (ff)", "{{flexural_frequency}}", "{{flexural_frequency_unc}}", "Hz"),
        ("Torsional Frequency (ft)", "{{torsional_frequency}}", "{{torsional_frequency_unc}}", "Hz"),
        ("Validity", "{{validity_status}}", "-", "-"),
    ]

    for i, row_data in enumerate(results_data):
        row = results_table.rows[i + 1]
        for j, text in enumerate(row_data):
            cell = row.cells[j]
            cell.text = text
            if j == 0:
                set_cell_shading(cell, 'F0F0F0')

    doc.add_paragraph()

    # Chart placeholder
    chart_heading = doc.add_paragraph()
    chart_heading.add_run("Velocity Measurements Chart").bold = True

    chart_para = doc.add_paragraph()
    chart_para.add_run("{{chart}}")
    chart_para.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_paragraph()

    # Validity Notes
    validity_heading = doc.add_paragraph()
    validity_heading.add_run("Notes").bold = True

    validity_para = doc.add_paragraph()
    validity_para.add_run("{{validity_notes}}")

    doc.add_paragraph()

    # Signatures table
    sig_heading = doc.add_paragraph()
    sig_heading.add_run("Approvals").bold = True

    sig_table = doc.add_table(rows=2, cols=6)
    sig_table.style = 'Table Grid'

    sig_headers = ["Tested By:", "{{tested_by}}", "Reviewed By:", "{{reviewed_by}}",
                   "Approved By:", "{{approved_by}}"]
    sig_dates = ["Date:", "{{tested_date}}", "Date:", "{{reviewed_date}}",
                 "Date:", "{{approved_date}}"]

    for i, text in enumerate(sig_headers):
        cell = sig_table.rows[0].cells[i]
        cell.text = text
        if i % 2 == 0:
            cell.paragraphs[0].runs[0].bold = True
            set_cell_shading(cell, 'E8E8E8')

    for i, text in enumerate(sig_dates):
        cell = sig_table.rows[1].cells[i]
        cell.text = text
        if i % 2 == 0:
            cell.paragraphs[0].runs[0].bold = True
            set_cell_shading(cell, 'E8E8E8')

    doc.add_paragraph()
    doc.add_paragraph()

    # Footer
    footer = doc.add_paragraph()
    footer.add_run("Durabler a part of Subseatec S AB, Address: Durabler C/O Subseatec, "
                   "Dalavägen 23, 68130 Kristinehamn, SWEDEN")
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.runs[0].font.size = Pt(8)
    footer.runs[0].italic = True

    # Save
    output_path = Path(__file__).parent.parent / "templates" / "sonic_e1875_report_template.docx"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_path)
    print(f"Template saved to: {output_path}")


if __name__ == "__main__":
    create_template()
