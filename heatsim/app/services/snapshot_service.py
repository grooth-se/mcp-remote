"""Service for creating immutable simulation snapshots."""
import json
from datetime import datetime

from app.extensions import db
from app.models.snapshot import SimulationSnapshot


class SnapshotService:
    """Creates immutable snapshots of simulation inputs at run time."""

    @staticmethod
    def create_snapshot(simulation):
        """Capture immutable snapshot of simulation + material state.

        Parameters
        ----------
        simulation : Simulation
            The simulation to snapshot

        Returns
        -------
        SimulationSnapshot
            The created snapshot (flushed, has ID)
        """
        max_version = db.session.query(
            db.func.coalesce(db.func.max(SimulationSnapshot.version), 0)
        ).filter(SimulationSnapshot.simulation_id == simulation.id).scalar()

        grade = simulation.steel_grade

        # Serialize material properties
        props = []
        for p in grade.properties.all():
            props.append({
                'name': p.property_name,
                'type': p.property_type,
                'units': p.units,
                'dependencies': p.dependencies,
                'data': p.data_dict,
                'notes': p.notes,
            })

        # Serialize phase diagram
        diagram = grade.phase_diagrams.first()
        diagram_data = None
        if diagram:
            diagram_data = {
                'type': diagram.diagram_type,
                'transformation_temps': diagram.temps_dict,
                'curves': diagram.curves_dict,
            }

        # Serialize composition
        comp_data = None
        if grade.composition:
            comp_data = grade.composition.to_dict()

        # Serialize phase properties
        phase_props = []
        for pp in grade.phase_properties.all():
            phase_props.append({
                'phase': pp.phase,
                'relative_density': pp.relative_density,
                'thermal_expansion_coeff': pp.thermal_expansion_coeff,
                'expansion_type': pp.expansion_type,
                'reference_temperature': pp.reference_temperature,
            })

        snapshot = SimulationSnapshot(
            simulation_id=simulation.id,
            version=max_version + 1,
            geometry_type=simulation.geometry_type,
            geometry_config=simulation.geometry_config,
            heat_treatment_config=simulation.heat_treatment_config,
            solver_config=simulation.solver_config,
            boundary_conditions=simulation.boundary_conditions,
            steel_grade_designation=grade.designation,
            steel_grade_data_source=grade.data_source,
            material_properties_snapshot=json.dumps(props),
            phase_diagram_snapshot=json.dumps(diagram_data),
            composition_snapshot=json.dumps(comp_data),
            phase_properties_snapshot=json.dumps(phase_props),
            cad_filename=simulation.cad_filename,
            cad_analysis=simulation.cad_analysis,
            cad_equivalent_type=getattr(simulation, 'cad_equivalent_type', None),
            user_id=simulation.user_id,
            started_at=datetime.utcnow(),
        )
        db.session.add(snapshot)
        db.session.flush()
        return snapshot

    @staticmethod
    def finalize_snapshot(snapshot, status, error_message=None):
        """Update snapshot with completion data.

        Parameters
        ----------
        snapshot : SimulationSnapshot
            The snapshot to finalize
        status : str
            'completed' or 'failed'
        error_message : str, optional
            Error message if failed
        """
        snapshot.completed_at = datetime.utcnow()
        snapshot.status = status
        snapshot.error_message = error_message
        if snapshot.started_at and snapshot.completed_at:
            snapshot.duration_seconds = (
                snapshot.completed_at - snapshot.started_at
            ).total_seconds()

    @staticmethod
    def update_summary(snapshot, results):
        """Update snapshot summary metrics from results.

        Parameters
        ----------
        snapshot : SimulationSnapshot
            The snapshot to update
        results : list of SimulationResult
            Results linked to this snapshot
        """
        for r in results:
            if r.t_800_500:
                snapshot.t_800_500 = r.t_800_500
            if r.result_type == 'hardness_prediction' and r.result_data:
                try:
                    data = json.loads(r.result_data)
                    if 'surface_hv' in data:
                        snapshot.predicted_hardness_surface = data['surface_hv']
                    if 'center_hv' in data:
                        snapshot.predicted_hardness_center = data['center_hv']
                except (json.JSONDecodeError, KeyError):
                    pass
