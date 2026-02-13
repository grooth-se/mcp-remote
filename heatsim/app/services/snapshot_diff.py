"""Service for comparing simulation snapshots."""
import json


class SnapshotDiffService:
    """Compares two simulation snapshots side-by-side."""

    @staticmethod
    def diff_configs(snap1, snap2):
        """Compare configuration fields between two snapshots.

        Returns
        -------
        list of dict
            [{field, label, val1, val2, changed}, ...]
        """
        diffs = []

        # Geometry
        diffs.append({
            'field': 'geometry_type',
            'label': 'Geometry Type',
            'val1': snap1.geometry_type,
            'val2': snap2.geometry_type,
            'changed': snap1.geometry_type != snap2.geometry_type,
        })

        # Compare geometry params
        geo1, geo2 = snap1.geometry_dict, snap2.geometry_dict
        all_keys = sorted(set(list(geo1.keys()) + list(geo2.keys())))
        for key in all_keys:
            v1, v2 = geo1.get(key), geo2.get(key)
            diffs.append({
                'field': f'geometry.{key}',
                'label': f'Geometry: {key}',
                'val1': v1,
                'val2': v2,
                'changed': v1 != v2,
            })

        # Compare HT config phases
        ht1, ht2 = snap1.ht_config, snap2.ht_config
        for phase_name in ['heating', 'transfer', 'quenching', 'tempering']:
            p1 = ht1.get(phase_name, {})
            p2 = ht2.get(phase_name, {})
            all_params = sorted(set(list(p1.keys()) + list(p2.keys())))
            for param in all_params:
                v1, v2 = p1.get(param), p2.get(param)
                diffs.append({
                    'field': f'ht.{phase_name}.{param}',
                    'label': f'{phase_name.title()}: {param.replace("_", " ").title()}',
                    'val1': v1,
                    'val2': v2,
                    'changed': v1 != v2,
                })

        # Compare solver config
        sol1, sol2 = snap1.solver_dict, snap2.solver_dict
        for key in sorted(set(list(sol1.keys()) + list(sol2.keys()))):
            v1, v2 = sol1.get(key), sol2.get(key)
            diffs.append({
                'field': f'solver.{key}',
                'label': f'Solver: {key.replace("_", " ").title()}',
                'val1': v1,
                'val2': v2,
                'changed': v1 != v2,
            })

        # Material
        diffs.append({
            'field': 'steel_grade',
            'label': 'Steel Grade',
            'val1': snap1.steel_grade_designation,
            'val2': snap2.steel_grade_designation,
            'changed': snap1.steel_grade_designation != snap2.steel_grade_designation,
        })

        return diffs

    @staticmethod
    def diff_materials(snap1, snap2):
        """Compare frozen material data between two snapshots.

        Returns
        -------
        list of dict
            [{field, label, val1, val2, changed}, ...]
        """
        diffs = []

        # Compare composition
        comp1 = snap1.composition_dict or {}
        comp2 = snap2.composition_dict or {}
        elements = sorted(set(list(comp1.keys()) + list(comp2.keys())))
        for elem in elements:
            if elem in ('source', 'notes', 'id', 'steel_grade_id'):
                continue
            v1, v2 = comp1.get(elem), comp2.get(elem)
            if v1 != v2:
                diffs.append({
                    'field': f'composition.{elem}',
                    'label': f'Composition: {elem}',
                    'val1': v1,
                    'val2': v2,
                    'changed': True,
                })

        # Compare transformation temperatures
        pd1 = snap1.phase_diagram_dict or {}
        pd2 = snap2.phase_diagram_dict or {}
        temps1 = pd1.get('transformation_temps', {}) if pd1 else {}
        temps2 = pd2.get('transformation_temps', {}) if pd2 else {}
        for temp_key in sorted(set(list(temps1.keys()) + list(temps2.keys()))):
            v1, v2 = temps1.get(temp_key), temps2.get(temp_key)
            if v1 != v2:
                diffs.append({
                    'field': f'phase_diagram.{temp_key}',
                    'label': f'Phase Diagram: {temp_key}',
                    'val1': v1,
                    'val2': v2,
                    'changed': True,
                })

        # Compare property count
        props1 = snap1.material_props_dict or []
        props2 = snap2.material_props_dict or []
        if len(props1) != len(props2):
            diffs.append({
                'field': 'properties_count',
                'label': 'Material Properties Count',
                'val1': len(props1),
                'val2': len(props2),
                'changed': True,
            })

        return diffs

    @staticmethod
    def get_overlay_data(snap1, snap2):
        """Get result data for overlay plotting.

        Returns
        -------
        dict with snap1_id, snap2_id keys
            Each contains list of cooling curve result_ids
        """
        from app.models import SimulationResult
        results1 = SimulationResult.query.filter_by(
            snapshot_id=snap1.id,
            result_type='full_cycle',
        ).all()
        results2 = SimulationResult.query.filter_by(
            snapshot_id=snap2.id,
            result_type='full_cycle',
        ).all()

        return {
            'snap1': {
                'version': snap1.version,
                'result_ids': [r.id for r in results1],
            },
            'snap2': {
                'version': snap2.version,
                'result_ids': [r.id for r in results2],
            },
        }

    @staticmethod
    def summary_comparison(snap1, snap2):
        """Compare summary metrics between snapshots.

        Returns
        -------
        list of dict
            [{label, val1, val2, delta, improved}, ...]
        """
        metrics = []

        if snap1.t_800_500 is not None or snap2.t_800_500 is not None:
            v1 = snap1.t_800_500
            v2 = snap2.t_800_500
            delta = None
            if v1 is not None and v2 is not None:
                delta = v2 - v1
            metrics.append({
                'label': 't8/5 (s)',
                'val1': f'{v1:.2f}' if v1 else '-',
                'val2': f'{v2:.2f}' if v2 else '-',
                'delta': f'{delta:+.2f}' if delta is not None else '-',
            })

        if snap1.predicted_hardness_surface is not None or snap2.predicted_hardness_surface is not None:
            v1 = snap1.predicted_hardness_surface
            v2 = snap2.predicted_hardness_surface
            delta = None
            if v1 is not None and v2 is not None:
                delta = v2 - v1
            metrics.append({
                'label': 'Surface Hardness (HV)',
                'val1': f'{v1:.0f}' if v1 else '-',
                'val2': f'{v2:.0f}' if v2 else '-',
                'delta': f'{delta:+.0f}' if delta is not None else '-',
            })

        if snap1.predicted_hardness_center is not None or snap2.predicted_hardness_center is not None:
            v1 = snap1.predicted_hardness_center
            v2 = snap2.predicted_hardness_center
            delta = None
            if v1 is not None and v2 is not None:
                delta = v2 - v1
            metrics.append({
                'label': 'Center Hardness (HV)',
                'val1': f'{v1:.0f}' if v1 else '-',
                'val2': f'{v2:.0f}' if v2 else '-',
                'delta': f'{delta:+.0f}' if delta is not None else '-',
            })

        return metrics
