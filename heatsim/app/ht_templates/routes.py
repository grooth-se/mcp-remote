"""Heat treatment templates routes."""
import json
from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy import or_

from . import ht_templates_bp
from .forms import TemplateForm, SaveAsTemplateForm
from app.extensions import db
from app.models import HeatTreatmentTemplate, Simulation


@ht_templates_bp.route('/')
@login_required
def index():
    """List all templates (user's own + public)."""
    # Get filter parameters
    category = request.args.get('category', '')
    show_mine = request.args.get('mine', '') == '1'

    # Base query: user's templates or public templates
    if show_mine:
        query = HeatTreatmentTemplate.query.filter_by(user_id=current_user.id)
    else:
        query = HeatTreatmentTemplate.query.filter(
            or_(
                HeatTreatmentTemplate.user_id == current_user.id,
                HeatTreatmentTemplate.is_public == True
            )
        )

    # Filter by category
    if category:
        query = query.filter_by(category=category)

    # Order by use count (most popular first), then by name
    templates = query.order_by(
        HeatTreatmentTemplate.use_count.desc(),
        HeatTreatmentTemplate.name
    ).all()

    return render_template(
        'ht_templates/index.html',
        templates=templates,
        categories=HeatTreatmentTemplate.CATEGORY_LABELS,
        selected_category=category,
        show_mine=show_mine
    )


@ht_templates_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new():
    """Create a new template from scratch."""
    form = TemplateForm()

    if form.validate_on_submit():
        # Create template with default heat treatment config
        template = HeatTreatmentTemplate(
            name=form.name.data,
            description=form.description.data,
            category=form.category.data,
            is_public=form.is_public.data,
            user_id=current_user.id,
        )
        # Set default config (same as Simulation defaults)
        template.set_ht_config(_get_default_ht_config())

        db.session.add(template)
        db.session.commit()

        flash(f'Template "{template.name}" created. Configure the heat treatment settings.', 'success')
        return redirect(url_for('ht_templates.edit', id=template.id))

    return render_template('ht_templates/new.html', form=form)


@ht_templates_bp.route('/<int:id>')
@login_required
def view(id):
    """View template details."""
    template = HeatTreatmentTemplate.query.get_or_404(id)

    # Check access
    if not template.is_public and template.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('ht_templates.index'))

    return render_template('ht_templates/view.html', template=template)


@ht_templates_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    """Edit template."""
    template = HeatTreatmentTemplate.query.get_or_404(id)

    # Only owner can edit
    if template.user_id != current_user.id:
        flash('You can only edit your own templates.', 'danger')
        return redirect(url_for('ht_templates.index'))

    form = TemplateForm(obj=template)

    if form.validate_on_submit():
        template.name = form.name.data
        template.description = form.description.data
        template.category = form.category.data
        template.is_public = form.is_public.data

        db.session.commit()
        flash(f'Template "{template.name}" updated.', 'success')
        return redirect(url_for('ht_templates.view', id=template.id))

    return render_template('ht_templates/edit.html', template=template, form=form)


@ht_templates_bp.route('/<int:id>/config', methods=['GET', 'POST'])
@login_required
def edit_config(id):
    """Edit template heat treatment configuration."""
    template = HeatTreatmentTemplate.query.get_or_404(id)

    # Only owner can edit
    if template.user_id != current_user.id:
        flash('You can only edit your own templates.', 'danger')
        return redirect(url_for('ht_templates.index'))

    if request.method == 'POST':
        # Parse form data into heat treatment config
        ht_config = _parse_ht_config_from_form(request.form)
        template.set_ht_config(ht_config)
        db.session.commit()

        flash('Heat treatment configuration updated.', 'success')
        return redirect(url_for('ht_templates.view', id=template.id))

    return render_template('ht_templates/edit_config.html', template=template)


@ht_templates_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    """Delete template."""
    template = HeatTreatmentTemplate.query.get_or_404(id)

    # Only owner can delete
    if template.user_id != current_user.id:
        flash('You can only delete your own templates.', 'danger')
        return redirect(url_for('ht_templates.index'))

    name = template.name
    db.session.delete(template)
    db.session.commit()

    flash(f'Template "{name}" deleted.', 'success')
    return redirect(url_for('ht_templates.index'))


@ht_templates_bp.route('/<int:id>/duplicate', methods=['POST'])
@login_required
def duplicate(id):
    """Duplicate a template (creates a copy owned by current user)."""
    template = HeatTreatmentTemplate.query.get_or_404(id)

    # Check access
    if not template.is_public and template.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('ht_templates.index'))

    # Create copy
    new_template = HeatTreatmentTemplate(
        name=f"{template.name} (Copy)",
        description=template.description,
        category=template.category,
        is_public=False,
        user_id=current_user.id,
        heat_treatment_config=template.heat_treatment_config,
        suggested_geometry_type=template.suggested_geometry_type,
        suggested_geometry_config=template.suggested_geometry_config,
        solver_config=template.solver_config,
    )

    db.session.add(new_template)
    db.session.commit()

    flash(f'Template duplicated as "{new_template.name}".', 'success')
    return redirect(url_for('ht_templates.edit', id=new_template.id))


@ht_templates_bp.route('/<int:id>/apply/<int:sim_id>', methods=['POST'])
@login_required
def apply_to_simulation(id, sim_id):
    """Apply template to an existing simulation."""
    template = HeatTreatmentTemplate.query.get_or_404(id)
    simulation = Simulation.query.get_or_404(sim_id)

    # Check access
    if not template.is_public and template.user_id != current_user.id:
        flash('Access denied to template.', 'danger')
        return redirect(url_for('simulation.view', id=sim_id))

    if simulation.user_id != current_user.id:
        flash('Access denied to simulation.', 'danger')
        return redirect(url_for('simulation.index'))

    # Apply template config to simulation
    simulation.heat_treatment_config = template.heat_treatment_config

    if template.solver_config:
        simulation.solver_config = template.solver_config

    # Update simulation status if it was draft
    if simulation.status == 'draft':
        simulation.status = 'ready'

    # Increment template use count
    template.increment_use_count()

    db.session.commit()

    flash(f'Template "{template.name}" applied to simulation.', 'success')
    return redirect(url_for('simulation.heat_treatment', id=sim_id))


@ht_templates_bp.route('/api/list')
@login_required
def api_list():
    """API endpoint to get templates for dropdown selection."""
    templates = HeatTreatmentTemplate.query.filter(
        or_(
            HeatTreatmentTemplate.user_id == current_user.id,
            HeatTreatmentTemplate.is_public == True
        )
    ).order_by(
        HeatTreatmentTemplate.use_count.desc(),
        HeatTreatmentTemplate.name
    ).all()

    return jsonify([
        {
            'id': t.id,
            'name': t.name,
            'category': t.category_label,
            'summary': t.get_summary(),
            'is_mine': t.user_id == current_user.id,
            'is_public': t.is_public,
        }
        for t in templates
    ])


def _get_default_ht_config():
    """Get default heat treatment configuration."""
    return {
        'heating': {
            'enabled': True,
            'initial_temperature': 25.0,
            'target_temperature': 850.0,
            'hold_time': 60.0,
            'furnace_atmosphere': 'air',
            'furnace_htc': 25.0,
            'furnace_emissivity': 0.85,
            'use_radiation': True,
        },
        'transfer': {
            'enabled': True,
            'duration': 10.0,
            'ambient_temperature': 25.0,
            'htc': 10.0,
            'emissivity': 0.85,
            'use_radiation': True,
        },
        'quenching': {
            'enabled': True,
            'media': 'water',
            'media_temperature': 25.0,
            'agitation': 'moderate',
            'htc_override': None,
            'duration': 300.0,
        },
        'tempering': {
            'enabled': False,
            'temperature': 550.0,
            'hold_time': 120.0,
            'cooling_method': 'air',
            'htc': 25.0,
        },
    }


def _parse_ht_config_from_form(form_data):
    """Parse heat treatment config from form data."""
    def get_float(key, default=0.0):
        try:
            return float(form_data.get(key, default))
        except (TypeError, ValueError):
            return default

    def get_bool(key):
        return form_data.get(key) == 'on' or form_data.get(key) == 'true'

    return {
        'heating': {
            'enabled': get_bool('heating_enabled'),
            'initial_temperature': get_float('heating_initial_temperature', 25.0),
            'target_temperature': get_float('heating_target_temperature', 850.0),
            'hold_time': get_float('heating_hold_time', 60.0),
            'furnace_atmosphere': form_data.get('heating_furnace_atmosphere', 'air'),
            'furnace_htc': get_float('heating_furnace_htc', 25.0),
            'furnace_emissivity': get_float('heating_furnace_emissivity', 0.85),
            'use_radiation': get_bool('heating_use_radiation'),
            'cold_furnace': get_bool('heating_cold_furnace'),
            'furnace_start_temperature': get_float('heating_furnace_start_temperature', 25.0),
            'furnace_ramp_rate': get_float('heating_furnace_ramp_rate', 5.0),
        },
        'transfer': {
            'enabled': get_bool('transfer_enabled'),
            'duration': get_float('transfer_duration', 10.0),
            'ambient_temperature': get_float('transfer_ambient_temperature', 25.0),
            'htc': get_float('transfer_htc', 10.0),
            'emissivity': get_float('transfer_emissivity', 0.85),
            'use_radiation': get_bool('transfer_use_radiation'),
        },
        'quenching': {
            'enabled': True,  # Always enabled
            'media': form_data.get('quenching_media', 'water'),
            'media_temperature': get_float('quenching_media_temperature', 25.0),
            'agitation': form_data.get('quenching_agitation', 'moderate'),
            'htc_override': get_float('quenching_htc_override') if form_data.get('quenching_htc_override') else None,
            'duration': get_float('quenching_duration', 300.0),
        },
        'tempering': {
            'enabled': get_bool('tempering_enabled'),
            'temperature': get_float('tempering_temperature', 550.0),
            'hold_time': get_float('tempering_hold_time', 120.0),
            'cooling_method': form_data.get('tempering_cooling_method', 'air'),
            'htc': get_float('tempering_htc', 25.0),
        },
    }
