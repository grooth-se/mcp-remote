"""Service for building simulation data lineage trees."""
import json


class LineageService:
    """Builds lineage tree from snapshot → material → config → results."""

    @staticmethod
    def build_lineage(snapshot):
        """Build nested lineage dict for a snapshot.

        Returns
        -------
        dict
            Nested tree: material → config → results
        """
        sim = snapshot.simulation

        # Material lineage
        material = {
            'designation': snapshot.steel_grade_designation,
            'data_source': snapshot.steel_grade_data_source,
            'composition': snapshot.composition_dict,
            'properties_count': len(snapshot.material_props_dict or []),
            'properties': snapshot.material_props_dict or [],
            'phase_diagram': snapshot.phase_diagram_dict,
            'phase_properties': snapshot.phase_props_dict or [],
        }

        # Config lineage
        config = {
            'geometry_type': snapshot.geometry_type,
            'geometry': snapshot.geometry_dict,
            'heat_treatment': snapshot.ht_config,
            'solver': snapshot.solver_dict,
            'cad_filename': snapshot.cad_filename,
        }

        # Results lineage
        from app.models import SimulationResult
        results_list = SimulationResult.query.filter_by(
            snapshot_id=snapshot.id
        ).all()

        result_types = {}
        for r in results_list:
            if r.result_type not in result_types:
                result_types[r.result_type] = 0
            result_types[r.result_type] += 1

        results = {
            'status': snapshot.status,
            'duration': snapshot.duration_seconds,
            't_800_500': snapshot.t_800_500,
            'hardness_surface': snapshot.predicted_hardness_surface,
            'hardness_center': snapshot.predicted_hardness_center,
            'result_types': result_types,
            'total_results': len(results_list),
        }

        return {
            'snapshot': {
                'version': snapshot.version,
                'started_at': snapshot.started_at,
                'completed_at': snapshot.completed_at,
            },
            'simulation': {
                'id': sim.id,
                'name': sim.name,
            },
            'material': material,
            'config': config,
            'results': results,
        }

    @staticmethod
    def check_drift(snapshot):
        """Compare frozen material data vs current DB state.

        Returns
        -------
        list of dict
            [{field, snapshot_value, current_value, drifted}, ...]
        """
        sim = snapshot.simulation
        grade = sim.steel_grade
        drifts = []

        # Check designation
        if snapshot.steel_grade_designation != grade.designation:
            drifts.append({
                'field': 'Steel Grade Designation',
                'snapshot_value': snapshot.steel_grade_designation,
                'current_value': grade.designation,
                'drifted': True,
            })

        # Check composition
        snap_comp = snapshot.composition_dict or {}
        current_comp = grade.composition.to_dict() if grade.composition else {}
        comp_elements = ['carbon', 'manganese', 'silicon', 'chromium', 'nickel',
                         'molybdenum', 'vanadium', 'tungsten', 'copper']
        for elem in comp_elements:
            sv = snap_comp.get(elem)
            cv = current_comp.get(elem)
            if sv != cv:
                drifts.append({
                    'field': f'Composition: {elem}',
                    'snapshot_value': sv,
                    'current_value': cv,
                    'drifted': True,
                })

        # Check transformation temps
        snap_pd = snapshot.phase_diagram_dict
        current_diagram = grade.phase_diagrams.first()
        snap_temps = (snap_pd.get('transformation_temps', {}) if snap_pd else {}) or {}
        current_temps = current_diagram.temps_dict if current_diagram else {}
        for key in sorted(set(list(snap_temps.keys()) + list(current_temps.keys()))):
            sv = snap_temps.get(key)
            cv = current_temps.get(key)
            if sv != cv:
                drifts.append({
                    'field': f'Phase Diagram: {key}',
                    'snapshot_value': sv,
                    'current_value': cv,
                    'drifted': True,
                })

        # Check property count
        snap_props = snapshot.material_props_dict or []
        current_props = grade.properties.all()
        if len(snap_props) != len(current_props):
            drifts.append({
                'field': 'Material Properties Count',
                'snapshot_value': len(snap_props),
                'current_value': len(current_props),
                'drifted': True,
            })

        return drifts
