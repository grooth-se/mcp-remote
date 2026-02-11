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
    SteelGrade, MaterialProperty, PhaseDiagram, PhaseProperty, SteelComposition,
    PROPERTY_TYPE_CONSTANT, PROPERTY_TYPE_CURVE,
    PROPERTY_TYPE_POLYNOMIAL, PROPERTY_TYPE_EQUATION,
    DATA_SOURCE_STANDARD,
    PHASES, PHASE_LABELS,
)
from app.services import PropertyEvaluator, PropertyPlotter, ExcelImporter, seed_standard_grades, seed_standard_compositions

from . import materials_bp
from .forms import (
    SteelGradeForm, MaterialPropertyForm, PhaseDiagramForm,
    ImportForm, PropertyEvaluateForm, PhasePropertyForm, SteelCompositionForm
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
# Phase Properties
# ============================================================================

@materials_bp.route('/<int:id>/phase-properties', methods=['GET', 'POST'])
@login_required
def phase_properties(id):
    """Manage phase-specific properties for a steel grade."""
    grade = SteelGrade.query.get_or_404(id)
    form = PhasePropertyForm()

    if form.validate_on_submit():
        # Check if phase property already exists
        existing = PhaseProperty.query.filter_by(
            steel_grade_id=grade.id,
            phase=form.phase.data
        ).first()

        # Parse expansion data if temperature-dependent
        expansion_data = None
        if form.expansion_type.data == 'temperature_dependent' and form.expansion_data.data:
            try:
                expansion_data = json.loads(form.expansion_data.data)
            except json.JSONDecodeError:
                flash('Invalid JSON for expansion data.', 'danger')
                return render_template('materials/phase_properties.html',
                                      form=form, grade=grade,
                                      phase_props=grade.phase_properties.all())

        # Convert expansion coefficient from µ/K to 1/K
        expansion_coeff = None
        if form.thermal_expansion_coeff.data is not None:
            expansion_coeff = form.thermal_expansion_coeff.data * 1e-6

        if existing:
            # Update existing
            existing.relative_density = form.relative_density.data
            existing.thermal_expansion_coeff = expansion_coeff
            existing.expansion_type = form.expansion_type.data
            if expansion_data:
                # Convert expansion data values from µ/K to 1/K
                if 'value' in expansion_data:
                    expansion_data['value'] = [v * 1e-6 for v in expansion_data['value']]
                existing.set_expansion_data(expansion_data)
            existing.reference_temperature = form.reference_temperature.data
            existing.notes = form.notes.data
            flash(f'Phase property for {PHASE_LABELS[form.phase.data]} updated.', 'success')
        else:
            # Create new
            pp = PhaseProperty(
                steel_grade_id=grade.id,
                phase=form.phase.data,
                relative_density=form.relative_density.data,
                thermal_expansion_coeff=expansion_coeff,
                expansion_type=form.expansion_type.data,
                reference_temperature=form.reference_temperature.data,
                notes=form.notes.data
            )
            if expansion_data:
                if 'value' in expansion_data:
                    expansion_data['value'] = [v * 1e-6 for v in expansion_data['value']]
                pp.set_expansion_data(expansion_data)
            db.session.add(pp)
            flash(f'Phase property for {PHASE_LABELS[form.phase.data]} created.', 'success')

        db.session.commit()
        return redirect(url_for('materials.phase_properties', id=grade.id))

    existing_props = grade.phase_properties.all()
    return render_template(
        'materials/phase_properties.html',
        form=form,
        grade=grade,
        phase_props=existing_props,
        phase_labels=PHASE_LABELS
    )


@materials_bp.route('/<int:id>/phase-properties/<int:pp_id>/delete', methods=['POST'])
@login_required
def delete_phase_property(id, pp_id):
    """Delete a phase property."""
    pp = PhaseProperty.query.get_or_404(pp_id)
    if pp.steel_grade_id != id:
        flash('Phase property not found.', 'danger')
        return redirect(url_for('materials.phase_properties', id=id))

    phase_label = pp.phase_label
    db.session.delete(pp)
    db.session.commit()

    flash(f'Phase property for {phase_label} deleted.', 'success')
    return redirect(url_for('materials.phase_properties', id=id))


# ============================================================================
# Steel Composition
# ============================================================================

@materials_bp.route('/<int:id>/composition', methods=['GET', 'POST'])
@login_required
def composition(id):
    """Manage chemical composition for a steel grade."""
    grade = SteelGrade.query.get_or_404(id)
    form = SteelCompositionForm()

    # Pre-populate form if composition exists
    existing = grade.composition
    if request.method == 'GET' and existing:
        form.carbon.data = existing.carbon
        form.manganese.data = existing.manganese
        form.silicon.data = existing.silicon
        form.chromium.data = existing.chromium
        form.nickel.data = existing.nickel
        form.molybdenum.data = existing.molybdenum
        form.vanadium.data = existing.vanadium
        form.tungsten.data = existing.tungsten
        form.copper.data = existing.copper
        form.phosphorus.data = existing.phosphorus
        form.sulfur.data = existing.sulfur
        form.nitrogen.data = existing.nitrogen
        form.boron.data = existing.boron
        form.source.data = existing.source
        form.notes.data = existing.notes

    if form.validate_on_submit():
        if existing:
            # Update existing
            existing.carbon = form.carbon.data
            existing.manganese = form.manganese.data or 0.0
            existing.silicon = form.silicon.data or 0.0
            existing.chromium = form.chromium.data or 0.0
            existing.nickel = form.nickel.data or 0.0
            existing.molybdenum = form.molybdenum.data or 0.0
            existing.vanadium = form.vanadium.data or 0.0
            existing.tungsten = form.tungsten.data or 0.0
            existing.copper = form.copper.data or 0.0
            existing.phosphorus = form.phosphorus.data or 0.0
            existing.sulfur = form.sulfur.data or 0.0
            existing.nitrogen = form.nitrogen.data or 0.0
            existing.boron = form.boron.data or 0.0
            existing.source = form.source.data
            existing.notes = form.notes.data
            flash('Composition updated.', 'success')
        else:
            # Create new
            comp = SteelComposition(
                steel_grade_id=grade.id,
                carbon=form.carbon.data,
                manganese=form.manganese.data or 0.0,
                silicon=form.silicon.data or 0.0,
                chromium=form.chromium.data or 0.0,
                nickel=form.nickel.data or 0.0,
                molybdenum=form.molybdenum.data or 0.0,
                vanadium=form.vanadium.data or 0.0,
                tungsten=form.tungsten.data or 0.0,
                copper=form.copper.data or 0.0,
                phosphorus=form.phosphorus.data or 0.0,
                sulfur=form.sulfur.data or 0.0,
                nitrogen=form.nitrogen.data or 0.0,
                boron=form.boron.data or 0.0,
                source=form.source.data,
                notes=form.notes.data
            )
            db.session.add(comp)
            flash('Composition created.', 'success')

        db.session.commit()
        return redirect(url_for('materials.view', id=grade.id))

    return render_template(
        'materials/composition.html',
        form=form,
        grade=grade,
        existing=existing
    )


@materials_bp.route('/<int:id>/composition/delete', methods=['POST'])
@login_required
def delete_composition(id):
    """Delete composition."""
    grade = SteelGrade.query.get_or_404(id)
    comp = grade.composition

    if comp:
        db.session.delete(comp)
        db.session.commit()
        flash('Composition deleted.', 'success')
    else:
        flash('No composition to delete.', 'warning')

    return redirect(url_for('materials.view', id=id))


# ============================================================================
# Property Plots
# ============================================================================

@materials_bp.route('/<int:id>/property/<int:prop_id>/plot')
@login_required
def property_plot(id, prop_id):
    """Generate and serve a plot of temperature-dependent property."""
    prop = MaterialProperty.query.get_or_404(prop_id)
    if prop.steel_grade_id != id:
        return '', 404

    # Only plot temperature-dependent properties
    if not prop.is_temperature_dependent and prop.property_type == 'constant':
        return '', 404

    plotter = PropertyPlotter()
    image_data = plotter.plot_property(prop)

    response = Response(image_data, mimetype='image/png')
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@materials_bp.route('/<int:id>/phase-plot/<plot_type>')
@login_required
def phase_plot(id, plot_type):
    """Generate and serve a plot of phase properties.

    Plot types:
    - density: Bar chart of relative densities
    - expansion: Bar chart of expansion coefficients
    - expansion_vs_temp: Line plot of expansion vs temperature
    """
    grade = SteelGrade.query.get_or_404(id)
    phase_props = grade.phase_properties.all()

    if not phase_props:
        return '', 404

    plotter = PropertyPlotter()

    if plot_type == 'density':
        image_data = plotter.plot_phase_properties(phase_props, property_type='density')
    elif plot_type == 'expansion':
        image_data = plotter.plot_phase_properties(phase_props, property_type='expansion')
    elif plot_type == 'expansion_vs_temp':
        image_data = plotter.plot_expansion_vs_temperature(phase_props)
    else:
        return '', 404

    response = Response(image_data, mimetype='image/png')
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


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
        f"{results['diagrams_created']} diagrams, "
        f"{results.get('phase_properties_created', 0)} phase properties"
    )
    flash(msg, 'success')
    return redirect(url_for('materials.index'))


@materials_bp.route('/seed-compositions', methods=['POST'])
@login_required
def seed_compositions():
    """Load standard chemical compositions."""
    results = seed_standard_compositions()

    if results['errors']:
        for error in results['errors'][:5]:
            flash(error, 'warning')

    msg = (
        f"Compositions seeded: {results['compositions_created']} created, "
        f"{results['compositions_skipped']} skipped (already exist)"
    )
    flash(msg, 'success')
    return redirect(url_for('materials.index'))
