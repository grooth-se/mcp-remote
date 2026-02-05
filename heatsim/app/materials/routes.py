"""Routes for materials management."""
import json
from flask import (
    render_template, redirect, url_for, flash, request,
    send_file, Response
)
from flask_login import login_required
from io import BytesIO

from app.extensions import db
from app.models import (
    SteelGrade, MaterialProperty, PhaseDiagram,
    PROPERTY_TYPE_CONSTANT, PROPERTY_TYPE_CURVE,
    PROPERTY_TYPE_POLYNOMIAL, PROPERTY_TYPE_EQUATION,
    DATA_SOURCE_STANDARD
)
from app.services import PropertyEvaluator, ExcelImporter, seed_standard_grades

from . import materials_bp
from .forms import (
    SteelGradeForm, MaterialPropertyForm, PhaseDiagramForm,
    ImportForm, PropertyEvaluateForm
)


# ============================================================================
# Steel Grade CRUD
# ============================================================================

@materials_bp.route('/')
@login_required
def index():
    """List all steel grades."""
    # Filters
    data_source = request.args.get('source', '')
    search = request.args.get('search', '')

    query = SteelGrade.query

    if data_source:
        query = query.filter_by(data_source=data_source)
    if search:
        query = query.filter(SteelGrade.designation.ilike(f'%{search}%'))

    grades = query.order_by(SteelGrade.designation).all()

    return render_template(
        'materials/index.html',
        grades=grades,
        current_source=data_source,
        search=search
    )


@materials_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new():
    """Create new steel grade."""
    form = SteelGradeForm()

    if form.validate_on_submit():
        # Check for duplicate
        existing = SteelGrade.query.filter_by(
            designation=form.designation.data,
            data_source=form.data_source.data
        ).first()

        if existing:
            flash('A steel grade with this designation and source already exists.', 'danger')
            return render_template('materials/new.html', form=form)

        grade = SteelGrade(
            designation=form.designation.data,
            data_source=form.data_source.data,
            description=form.description.data
        )
        db.session.add(grade)
        db.session.commit()

        flash(f'Steel grade {grade.designation} created successfully.', 'success')
        return redirect(url_for('materials.view', id=grade.id))

    return render_template('materials/new.html', form=form)


@materials_bp.route('/<int:id>')
@login_required
def view(id):
    """View steel grade details."""
    grade = SteelGrade.query.get_or_404(id)
    properties = grade.properties.all()
    diagrams = grade.phase_diagrams.all()

    # Evaluation form for temperature-dependent properties
    eval_form = PropertyEvaluateForm()

    return render_template(
        'materials/view.html',
        grade=grade,
        properties=properties,
        diagrams=diagrams,
        eval_form=eval_form
    )


@materials_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    """Edit steel grade."""
    grade = SteelGrade.query.get_or_404(id)
    form = SteelGradeForm(obj=grade)

    if form.validate_on_submit():
        # Check for duplicate (excluding current)
        existing = SteelGrade.query.filter(
            SteelGrade.id != id,
            SteelGrade.designation == form.designation.data,
            SteelGrade.data_source == form.data_source.data
        ).first()

        if existing:
            flash('Another steel grade with this designation and source exists.', 'danger')
            return render_template('materials/edit.html', form=form, grade=grade)

        grade.designation = form.designation.data
        grade.data_source = form.data_source.data
        grade.description = form.description.data
        db.session.commit()

        flash(f'Steel grade {grade.designation} updated successfully.', 'success')
        return redirect(url_for('materials.view', id=grade.id))

    return render_template('materials/edit.html', form=form, grade=grade)


@materials_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    """Delete steel grade."""
    grade = SteelGrade.query.get_or_404(id)
    designation = grade.designation

    db.session.delete(grade)
    db.session.commit()

    flash(f'Steel grade {designation} deleted successfully.', 'success')
    return redirect(url_for('materials.index'))


# ============================================================================
# Material Properties
# ============================================================================

@materials_bp.route('/<int:id>/properties', methods=['GET', 'POST'])
@login_required
def properties(id):
    """Manage properties for a steel grade."""
    grade = SteelGrade.query.get_or_404(id)
    form = MaterialPropertyForm()

    if form.validate_on_submit():
        # Determine property name
        prop_name = form.property_name.data
        if prop_name == 'custom' and form.custom_name.data:
            prop_name = form.custom_name.data.lower().replace(' ', '_')

        # Build data based on property type
        prop_type = form.property_type.data
        data = {}

        if prop_type == PROPERTY_TYPE_CONSTANT:
            data = {'value': form.constant_value.data}
        elif prop_type == PROPERTY_TYPE_CURVE:
            try:
                data = json.loads(form.curve_data.data) if form.curve_data.data else {}
            except json.JSONDecodeError:
                flash('Invalid JSON for curve data.', 'danger')
                return render_template('materials/properties.html', form=form, grade=grade)
        elif prop_type == PROPERTY_TYPE_POLYNOMIAL:
            coeffs = []
            if form.polynomial_coefficients.data:
                coeffs = [float(c.strip()) for c in form.polynomial_coefficients.data.split(',')]
            data = {
                'variable': form.polynomial_variable.data or 'temperature',
                'coefficients': coeffs
            }
        elif prop_type == PROPERTY_TYPE_EQUATION:
            variables = {}
            if form.equation_variables.data:
                try:
                    variables = json.loads(form.equation_variables.data)
                except json.JSONDecodeError:
                    flash('Invalid JSON for equation variables.', 'danger')
                    return render_template('materials/properties.html', form=form, grade=grade)
            data = {
                'equation': form.equation.data,
                'variables': variables
            }

        # Check if property already exists
        existing = MaterialProperty.query.filter_by(
            steel_grade_id=grade.id,
            property_name=prop_name
        ).first()

        if existing:
            # Update existing
            existing.property_type = prop_type
            existing.units = form.units.data
            existing.dependencies = form.dependencies.data
            existing.notes = form.notes.data
            existing.set_data(data)
            flash(f'Property {prop_name} updated.', 'success')
        else:
            # Create new
            prop = MaterialProperty(
                steel_grade_id=grade.id,
                property_name=prop_name,
                property_type=prop_type,
                units=form.units.data,
                dependencies=form.dependencies.data,
                notes=form.notes.data
            )
            prop.set_data(data)
            db.session.add(prop)
            flash(f'Property {prop_name} created.', 'success')

        db.session.commit()
        return redirect(url_for('materials.properties', id=grade.id))

    existing_props = grade.properties.all()
    return render_template(
        'materials/properties.html',
        form=form,
        grade=grade,
        properties=existing_props
    )


@materials_bp.route('/<int:id>/properties/<int:prop_id>/delete', methods=['POST'])
@login_required
def delete_property(id, prop_id):
    """Delete a material property."""
    prop = MaterialProperty.query.get_or_404(prop_id)
    if prop.steel_grade_id != id:
        flash('Property not found.', 'danger')
        return redirect(url_for('materials.properties', id=id))

    name = prop.property_name
    db.session.delete(prop)
    db.session.commit()

    flash(f'Property {name} deleted.', 'success')
    return redirect(url_for('materials.properties', id=id))


@materials_bp.route('/<int:id>/evaluate', methods=['POST'])
@login_required
def evaluate_property(id):
    """Evaluate a property at given conditions."""
    grade = SteelGrade.query.get_or_404(id)
    form = PropertyEvaluateForm()

    prop_id = request.form.get('property_id')
    temperature = request.form.get('temperature')

    if not prop_id:
        flash('No property selected.', 'warning')
        return redirect(url_for('materials.view', id=id))

    prop = MaterialProperty.query.get_or_404(int(prop_id))

    try:
        temp_value = float(temperature) if temperature else None
        evaluator = PropertyEvaluator(prop)
        result = evaluator.evaluate(temperature=temp_value)

        if result is not None:
            flash(f'{prop.display_name} at {temp_value}°C = {result:.4g} {prop.units or ""}', 'info')
        else:
            flash('Could not evaluate property at given conditions.', 'warning')
    except Exception as e:
        flash(f'Evaluation error: {str(e)}', 'danger')

    return redirect(url_for('materials.view', id=id))


# ============================================================================
# Phase Diagrams
# ============================================================================

@materials_bp.route('/<int:id>/phase-diagram', methods=['GET', 'POST'])
@login_required
def phase_diagram(id):
    """Manage phase diagram for a steel grade."""
    grade = SteelGrade.query.get_or_404(id)
    form = PhaseDiagramForm()

    # Pre-populate form if diagram exists
    existing = grade.phase_diagrams.first()
    if request.method == 'GET' and existing:
        form.diagram_type.data = existing.diagram_type
        temps = existing.temps_dict
        form.ac1.data = temps.get('Ac1')
        form.ac3.data = temps.get('Ac3')
        form.ms.data = temps.get('Ms')
        form.mf.data = temps.get('Mf')
        form.bs.data = temps.get('Bs')
        form.bf.data = temps.get('Bf')
        form.curves_data.data = existing.curves if existing.curves else ''

    if form.validate_on_submit():
        # Build transformation temps dict
        temps = {}
        if form.ac1.data is not None:
            temps['Ac1'] = form.ac1.data
        if form.ac3.data is not None:
            temps['Ac3'] = form.ac3.data
        if form.ms.data is not None:
            temps['Ms'] = form.ms.data
        if form.mf.data is not None:
            temps['Mf'] = form.mf.data
        if form.bs.data is not None:
            temps['Bs'] = form.bs.data
        if form.bf.data is not None:
            temps['Bf'] = form.bf.data

        # Parse curves if provided
        curves = None
        if form.curves_data.data:
            try:
                curves = json.loads(form.curves_data.data)
            except json.JSONDecodeError:
                flash('Invalid JSON for curves data.', 'danger')
                return render_template('materials/phase_diagram.html', form=form, grade=grade)

        # Handle image upload
        image_data = None
        if form.source_image.data:
            image_data = form.source_image.data.read()

        if existing:
            # Update existing
            existing.diagram_type = form.diagram_type.data
            existing.set_temps(temps)
            if curves:
                existing.set_curves(curves)
            if image_data:
                existing.source_image = image_data
            flash('Phase diagram updated.', 'success')
        else:
            # Create new
            diagram = PhaseDiagram(
                steel_grade_id=grade.id,
                diagram_type=form.diagram_type.data,
                source_image=image_data
            )
            diagram.set_temps(temps)
            if curves:
                diagram.set_curves(curves)
            db.session.add(diagram)
            flash('Phase diagram created.', 'success')

        db.session.commit()
        return redirect(url_for('materials.view', id=grade.id))

    return render_template(
        'materials/phase_diagram.html',
        form=form,
        grade=grade,
        existing=existing
    )


@materials_bp.route('/<int:id>/phase-diagram/image')
@login_required
def phase_diagram_image(id):
    """Serve phase diagram image."""
    grade = SteelGrade.query.get_or_404(id)
    diagram = grade.phase_diagrams.first()

    if not diagram or not diagram.source_image:
        return '', 404

    return Response(diagram.source_image, mimetype='image/png')


@materials_bp.route('/<int:id>/phase-diagram/delete', methods=['POST'])
@login_required
def delete_phase_diagram(id):
    """Delete phase diagram."""
    grade = SteelGrade.query.get_or_404(id)
    diagram = grade.phase_diagrams.first()

    if diagram:
        db.session.delete(diagram)
        db.session.commit()
        flash('Phase diagram deleted.', 'success')
    else:
        flash('No phase diagram to delete.', 'warning')

    return redirect(url_for('materials.view', id=id))


# ============================================================================
# Import/Export
# ============================================================================

@materials_bp.route('/import', methods=['GET', 'POST'])
@login_required
def import_data():
    """Import material data from Excel."""
    form = ImportForm()

    if form.validate_on_submit():
        results = ExcelImporter.import_from_excel(
            form.file.data,
            data_source=form.data_source.data
        )

        if results['errors']:
            for error in results['errors'][:5]:  # Show first 5 errors
                flash(error, 'warning')

        msg = (
            f"Import complete: {results['grades_created']} grades created, "
            f"{results['grades_updated']} updated, "
            f"{results['properties_created']} properties, "
            f"{results['diagrams_created']} diagrams"
        )
        flash(msg, 'success')
        return redirect(url_for('materials.index'))

    return render_template('materials/import.html', form=form)


@materials_bp.route('/<int:id>/export')
@login_required
def export(id):
    """Export single steel grade to Excel."""
    grade = SteelGrade.query.get_or_404(id)
    excel_data = ExcelImporter.export_to_excel([id])

    return send_file(
        BytesIO(excel_data),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'{grade.designation.replace(" ", "_")}_material_data.xlsx'
    )


@materials_bp.route('/export-all')
@login_required
def export_all():
    """Export all steel grades to Excel."""
    excel_data = ExcelImporter.export_to_excel()

    return send_file(
        BytesIO(excel_data),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='all_material_data.xlsx'
    )


@materials_bp.route('/template')
@login_required
def download_template():
    """Download Excel import template."""
    template_data = ExcelImporter.get_template()

    return send_file(
        BytesIO(template_data),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='material_import_template.xlsx'
    )


# ============================================================================
# Seed Data
# ============================================================================

@materials_bp.route('/seed', methods=['POST'])
@login_required
def seed():
    """Load 20 standard steel grades."""
    results = seed_standard_grades()

    if results['errors']:
        for error in results['errors'][:5]:
            flash(error, 'warning')

    msg = (
        f"Seed complete: {results['grades_created']} grades created, "
        f"{results['grades_skipped']} skipped (already exist), "
        f"{results['properties_created']} properties, "
        f"{results['diagrams_created']} diagrams"
    )
    flash(msg, 'success')
    return redirect(url_for('materials.index'))
