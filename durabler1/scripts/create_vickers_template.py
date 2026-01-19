"""
Create Vickers Hardness Report Template for ASTM E92.

This script creates a Word document template with placeholders
for the Vickers hardness test report.
"""

from pathlib import Path
from docx import Document
from docx.shared import Inches, Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


def set_cell_shading(cell, color):
    """Set cell background color."""
    shading = OxmlElement('w:shd')
    shading.set(qn('w:fill'), color)
    cell._tc.get_or_add_tcPr().append(shading)


def create_vickers_template():
    """Create Vickers hardness report template."""
    doc = Document()

    # Set narrow margins
    sections = doc.sections
    for section in sections:
        section.top_margin = Cm(1.5)
        section.bottom_margin = Cm(1.5)
        section.left_margin = Cm(2)
        section.right_margin = Cm(2)

    # Header with logo placeholder
    header = doc.sections[0].header
    header_para = header.paragraphs[0]
    header_para.text = "{{logo}}"
    header_para.alignment = WD_ALIGN_PARAGRAPH.LEFT

    # Title
    title = doc.add_paragraph()
    title_run = title.add_run("VICKERS HARDNESS TEST REPORT")
    title_run.bold = True
    title_run.font.size = Pt(16)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Subtitle
    subtitle = doc.add_paragraph()
    subtitle_run = subtitle.add_run("ASTM E92 / ISO 6507-1")
    subtitle_run.font.size = Pt(11)
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_paragraph()

    # Report information table
    report_table = doc.add_table(rows=2, cols=4)
    report_table.style = 'Table Grid'

    headers = ['Report Number', 'Report Date', 'Certificate No.', 'Load Level']
    values = ['{{report_number}}', '{{report_date}}', '{{certificate_number}}', '{{load_level}}']

    for i, (header, value) in enumerate(zip(headers, values)):
        cell = report_table.rows[0].cells[i]
        cell.text = header
        set_cell_shading(cell, 'D9E2F3')
        cell.paragraphs[0].runs[0].bold = True

        report_table.rows[1].cells[i].text = value

    doc.add_paragraph()

    # Test Information section
    info_heading = doc.add_paragraph()
    info_run = info_heading.add_run("Test Information")
    info_run.bold = True
    info_run.font.size = Pt(12)

    info_table = doc.add_table(rows=4, cols=4)
    info_table.style = 'Table Grid'

    info_data = [
        ('Test Project:', '{{test_project}}', 'Customer:', '{{customer}}'),
        ('Specimen ID:', '{{specimen_id}}', 'Material:', '{{material}}'),
        ('Test Date:', '{{test_date}}', 'Operator:', '{{operator}}'),
    ]

    for row_idx, row_data in enumerate(info_data):
        for col_idx, text in enumerate(row_data):
            cell = info_table.rows[row_idx].cells[col_idx]
            cell.text = text
            if col_idx % 2 == 0:  # Header cells
                set_cell_shading(cell, 'F2F2F2')
                cell.paragraphs[0].runs[0].bold = True

    doc.add_paragraph()

    # Results section
    results_heading = doc.add_paragraph()
    results_run = results_heading.add_run("Test Results")
    results_run.bold = True
    results_run.font.size = Pt(12)

    results_table = doc.add_table(rows=7, cols=4)
    results_table.style = 'Table Grid'

    # Results table header
    header_row = results_table.rows[0]
    headers = ['Parameter', 'Value', 'Uncertainty U (k=2)', 'Unit']
    for i, header in enumerate(headers):
        cell = header_row.cells[i]
        cell.text = header
        set_cell_shading(cell, 'D9E2F3')
        cell.paragraphs[0].runs[0].bold = True

    # Results data
    results_data = [
        ('Mean Hardness', '{{mean_hardness}}', '± {{uncertainty}}', '{{unit}}'),
        ('Standard Deviation', '{{std_dev}}', '-', '{{unit}}'),
        ('Range (Max - Min)', '{{range}}', '-', '{{unit}}'),
        ('Minimum Value', '{{min_value}}', '-', '{{unit}}'),
        ('Maximum Value', '{{max_value}}', '-', '{{unit}}'),
        ('Number of Readings', '{{n_readings}}', '-', '-'),
    ]

    for row_idx, row_data in enumerate(results_data):
        for col_idx, text in enumerate(row_data):
            results_table.rows[row_idx + 1].cells[col_idx].text = text

    doc.add_paragraph()

    # Uncertainty Budget section
    unc_heading = doc.add_paragraph()
    unc_run = unc_heading.add_run("Uncertainty Budget (ISO 17025 / GUM)")
    unc_run.bold = True
    unc_run.font.size = Pt(12)

    unc_table = doc.add_table(rows=7, cols=3)
    unc_table.style = 'Table Grid'

    # Uncertainty table header
    unc_headers = ['Source', 'Type', 'Value (HV)']
    for i, header in enumerate(unc_headers):
        cell = unc_table.rows[0].cells[i]
        cell.text = header
        set_cell_shading(cell, 'D9E2F3')
        cell.paragraphs[0].runs[0].bold = True

    unc_data = [
        ('Repeatability (std of mean)', 'A', '{{u_A}}'),
        ('Machine calibration', 'B', '{{u_machine}}'),
        ('Diagonal measurement', 'B', '{{u_diagonal}}'),
        ('Force application', 'B', '{{u_force}}'),
        ('Combined standard uncertainty', '-', '{{u_combined}}'),
        ('Expanded uncertainty (k={{k}})', '-', '{{U_expanded}}'),
    ]

    for row_idx, row_data in enumerate(unc_data):
        for col_idx, text in enumerate(row_data):
            cell = unc_table.rows[row_idx + 1].cells[col_idx]
            cell.text = text
            if row_idx >= 4:  # Highlight combined/expanded rows
                set_cell_shading(cell, 'FFF2CC')

    doc.add_paragraph()

    # Hardness Profile Chart
    chart_heading = doc.add_paragraph()
    chart_run = chart_heading.add_run("Hardness Profile")
    chart_run.bold = True
    chart_run.font.size = Pt(12)

    chart_para = doc.add_paragraph("{{chart}}")
    chart_para.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_paragraph()

    # Indent Photo
    photo_heading = doc.add_paragraph()
    photo_run = photo_heading.add_run("Indent Photograph")
    photo_run.bold = True
    photo_run.font.size = Pt(12)

    photo_para = doc.add_paragraph("{{photo}}")
    photo_para.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_paragraph()

    # Signatures section
    sig_heading = doc.add_paragraph()
    sig_run = sig_heading.add_run("Signatures")
    sig_run.bold = True
    sig_run.font.size = Pt(12)

    sig_table = doc.add_table(rows=2, cols=3)
    sig_table.style = 'Table Grid'

    sig_headers = ['Tested By', 'Reviewed By', 'Approved By']
    for i, header in enumerate(sig_headers):
        cell = sig_table.rows[0].cells[i]
        cell.text = header
        set_cell_shading(cell, 'F2F2F2')
        cell.paragraphs[0].runs[0].bold = True

    # Empty signature cells
    for i in range(3):
        sig_table.rows[1].cells[i].text = "\n\n\n"

    # Footer
    footer = doc.sections[0].footer
    footer_para = footer.paragraphs[0]
    footer_para.text = "Report generated by Durabler - ISO 17025 Compliant Mechanical Testing System"
    footer_para.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Save template
    template_dir = Path(__file__).parent.parent / "templates"
    template_dir.mkdir(exist_ok=True)
    template_path = template_dir / "vickers_e92_report_template.docx"
    doc.save(template_path)

    print(f"Template created: {template_path}")
    return template_path


if __name__ == "__main__":
    create_vickers_template()
