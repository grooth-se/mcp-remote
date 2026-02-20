"""Tests for materials blueprint routes."""
import io
import json
import pytest
from app.models import (
    SteelGrade, MaterialProperty, PhaseDiagram, PhaseProperty, SteelComposition,
    DATA_SOURCE_STANDARD, DATA_SOURCE_SUBSEATEC,
)
from app.models.material_changelog import MaterialChangeLog


class TestSteelGradeIndex:
    def test_renders(self, logged_in_client, sample_steel_grade):
        rv = logged_in_client.get('/materials/')
        assert rv.status_code == 200
        assert b'AISI 4340' in rv.data

    def test_search_filter(self, logged_in_client, sample_steel_grade):
        rv = logged_in_client.get('/materials/?search=4340')
        assert rv.status_code == 200
        assert b'AISI 4340' in rv.data

    def test_source_filter(self, logged_in_client, sample_steel_grade):
        rv = logged_in_client.get('/materials/?source=Standard')
        assert rv.status_code == 200

    def test_requires_login(self, client, db):
        rv = client.get('/materials/')
        assert rv.status_code == 302


class TestSteelGradeNew:
    def test_form_renders(self, logged_in_client):
        rv = logged_in_client.get('/materials/new')
        assert rv.status_code == 200

    def test_create_success(self, logged_in_client, db):
        rv = logged_in_client.post('/materials/new', data={
            'designation': 'A182 F22',
            'data_source': DATA_SOURCE_STANDARD,
            'description': 'Alloy steel',
        }, follow_redirects=True)
        assert rv.status_code == 200
        assert SteelGrade.query.filter_by(designation='A182 F22').first() is not None

    def test_duplicate_rejection(self, logged_in_client, sample_steel_grade, db):
        rv = logged_in_client.post('/materials/new', data={
            'designation': 'AISI 4340',
            'data_source': DATA_SOURCE_STANDARD,
        }, follow_redirects=True)
        assert rv.status_code == 200


class TestSteelGradeView:
    def test_renders(self, logged_in_client, sample_steel_grade):
        rv = logged_in_client.get(f'/materials/{sample_steel_grade.id}')
        assert rv.status_code == 200
        assert b'AISI 4340' in rv.data

    def test_404(self, logged_in_client):
        rv = logged_in_client.get('/materials/99999')
        assert rv.status_code == 404


class TestSteelGradeEdit:
    def test_form_renders(self, logged_in_client, sample_steel_grade):
        rv = logged_in_client.get(f'/materials/{sample_steel_grade.id}/edit')
        assert rv.status_code == 200

    def test_update(self, logged_in_client, sample_steel_grade, db):
        rv = logged_in_client.post(f'/materials/{sample_steel_grade.id}/edit', data={
            'designation': 'AISI 4340 Modified',
            'data_source': DATA_SOURCE_STANDARD,
            'description': 'Updated',
        }, follow_redirects=True)
        assert rv.status_code == 200
        g = db.session.get(SteelGrade, sample_steel_grade.id)
        assert g.description == 'Updated'


class TestSteelGradeDelete:
    def test_success(self, logged_in_client, sample_steel_grade, db):
        gid = sample_steel_grade.id
        rv = logged_in_client.post(f'/materials/{gid}/delete', follow_redirects=True)
        assert rv.status_code == 200
        assert db.session.get(SteelGrade, gid) is None


class TestSeed:
    def test_seed(self, logged_in_client, db):
        rv = logged_in_client.post('/materials/seed', follow_redirects=True)
        assert rv.status_code == 200
        assert SteelGrade.query.count() > 0

    def test_seed_compositions(self, logged_in_client, db):
        # Seed grades first, then compositions
        logged_in_client.post('/materials/seed')
        rv = logged_in_client.post('/materials/seed-compositions', follow_redirects=True)
        assert rv.status_code == 200


class TestProperties:
    def test_page_renders(self, logged_in_client, sample_steel_grade):
        rv = logged_in_client.get(f'/materials/{sample_steel_grade.id}/properties')
        assert rv.status_code == 200

    def test_create_constant(self, logged_in_client, sample_steel_grade, db):
        rv = logged_in_client.post(f'/materials/{sample_steel_grade.id}/properties', data={
            'property_name': 'density',
            'property_type': 'constant',
            'units': 'kg/m³',
            'constant_value': '7850',
            'notes': '',
        }, follow_redirects=True)
        assert rv.status_code == 200
        prop = MaterialProperty.query.filter_by(
            steel_grade_id=sample_steel_grade.id,
            property_name='density'
        ).first()
        assert prop is not None

    def test_create_curve(self, logged_in_client, sample_steel_grade, db):
        curve_data = json.dumps({'temperature': [20, 200, 400], 'value': [46, 44, 40]})
        rv = logged_in_client.post(f'/materials/{sample_steel_grade.id}/properties', data={
            'property_name': 'thermal_conductivity',
            'property_type': 'curve',
            'units': 'W/(m·K)',
            'dependencies': 'temperature',
            'curve_data': curve_data,
            'notes': '',
        }, follow_redirects=True)
        assert rv.status_code == 200

    def test_create_polynomial(self, logged_in_client, sample_steel_grade, db):
        rv = logged_in_client.post(f'/materials/{sample_steel_grade.id}/properties', data={
            'property_name': 'specific_heat',
            'property_type': 'polynomial',
            'units': 'J/(kg·K)',
            'polynomial_variable': 'T',
            'polynomial_coefficients': '450,0.5',
            'notes': '',
        }, follow_redirects=True)
        assert rv.status_code == 200

    def test_delete_property(self, logged_in_client, sample_steel_grade, db):
        prop = MaterialProperty(
            steel_grade_id=sample_steel_grade.id,
            property_name='test_prop',
            property_type='constant',
            data=json.dumps({'value': 1.0}),
        )
        db.session.add(prop)
        db.session.commit()
        pid = prop.id
        rv = logged_in_client.post(
            f'/materials/{sample_steel_grade.id}/properties/{pid}/delete',
            follow_redirects=True)
        assert rv.status_code == 200
        assert db.session.get(MaterialProperty, pid) is None


class TestPhaseDiagram:
    def test_create(self, logged_in_client, sample_steel_grade, db):
        rv = logged_in_client.post(f'/materials/{sample_steel_grade.id}/phase-diagram', data={
            'diagram_type': 'CCT',
            'ac1': '720',
            'ac3': '810',
            'ms': '330',
            'mf': '150',
            'bs': '',
            'bf': '',
            'curves_data': '',
        }, follow_redirects=True)
        assert rv.status_code == 200
        pd = PhaseDiagram.query.filter_by(steel_grade_id=sample_steel_grade.id).first()
        assert pd is not None
        assert pd.diagram_type == 'CCT'

    def test_page_renders(self, logged_in_client, sample_steel_grade):
        rv = logged_in_client.get(f'/materials/{sample_steel_grade.id}/phase-diagram')
        assert rv.status_code == 200

    def test_delete(self, logged_in_client, sample_steel_grade, db):
        pd = PhaseDiagram(
            steel_grade_id=sample_steel_grade.id,
            diagram_type='TTT',
            transformation_temps=json.dumps({'Ac1': 720}),
        )
        db.session.add(pd)
        db.session.commit()
        rv = logged_in_client.post(
            f'/materials/{sample_steel_grade.id}/phase-diagram/delete',
            follow_redirects=True)
        assert rv.status_code == 200

    def test_image_upload(self, logged_in_client, sample_steel_grade, db):
        # Create a small PNG-like bytes
        fake_png = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        rv = logged_in_client.post(f'/materials/{sample_steel_grade.id}/phase-diagram', data={
            'diagram_type': 'CCT',
            'ac1': '720',
            'ac3': '810',
            'ms': '330',
            'mf': '150',
            'bs': '',
            'bf': '',
            'curves_data': '',
            'source_image': (io.BytesIO(fake_png), 'diagram.png'),
        }, content_type='multipart/form-data', follow_redirects=True)
        assert rv.status_code == 200


class TestPhaseProperties:
    def test_create_constant(self, logged_in_client, sample_steel_grade, db):
        rv = logged_in_client.post(f'/materials/{sample_steel_grade.id}/phase-properties', data={
            'phase': 'ferrite',
            'relative_density': '1.0',
            'thermal_expansion_coeff': '12e-6',
            'expansion_type': 'constant',
            'expansion_data': '',
            'reference_temperature': '20',
            'notes': '',
        }, follow_redirects=True)
        assert rv.status_code == 200

    def test_page_renders(self, logged_in_client, sample_steel_grade):
        rv = logged_in_client.get(f'/materials/{sample_steel_grade.id}/phase-properties')
        assert rv.status_code == 200

    def test_delete(self, logged_in_client, sample_steel_grade, db):
        pp = PhaseProperty(
            steel_grade_id=sample_steel_grade.id,
            phase='martensite',
            relative_density=0.98,
            thermal_expansion_coeff=10.5e-6,
        )
        db.session.add(pp)
        db.session.commit()
        rv = logged_in_client.post(
            f'/materials/{sample_steel_grade.id}/phase-properties/{pp.id}/delete',
            follow_redirects=True)
        assert rv.status_code == 200


class TestComposition:
    def test_page_renders(self, logged_in_client, sample_steel_grade):
        rv = logged_in_client.get(f'/materials/{sample_steel_grade.id}/composition')
        assert rv.status_code == 200

    def test_create(self, logged_in_client, sample_steel_grade, db):
        rv = logged_in_client.post(f'/materials/{sample_steel_grade.id}/composition', data={
            'carbon': '0.40',
            'manganese': '0.70',
            'silicon': '0.25',
            'chromium': '0.80',
            'nickel': '1.80',
            'molybdenum': '0.25',
            'vanadium': '0',
            'tungsten': '0',
            'copper': '0',
            'phosphorus': '0',
            'sulfur': '0',
            'nitrogen': '0',
            'boron': '0',
            'source': 'ASTM A29',
            'notes': '',
        }, follow_redirects=True)
        assert rv.status_code == 200
        comp = SteelComposition.query.filter_by(
            steel_grade_id=sample_steel_grade.id).first()
        assert comp is not None
        assert comp.carbon == 0.40

    def test_delete(self, logged_in_client, sample_steel_grade, db):
        comp = SteelComposition(
            steel_grade_id=sample_steel_grade.id,
            carbon=0.40,
        )
        db.session.add(comp)
        db.session.commit()
        rv = logged_in_client.post(
            f'/materials/{sample_steel_grade.id}/composition/delete',
            follow_redirects=True)
        assert rv.status_code == 200

    def test_composition_form_hp_field(self, logged_in_client, sample_steel_grade):
        """Composition form should render the Hollomon-Jaffe Hp field."""
        rv = logged_in_client.get(f'/materials/{sample_steel_grade.id}/composition')
        assert rv.status_code == 200
        assert b'Hollomon-Jaffe' in rv.data

    def test_composition_route_saves_hp(self, logged_in_client, sample_steel_grade, db):
        """POST with Hp value should persist hollomon_jaffe_c."""
        rv = logged_in_client.post(f'/materials/{sample_steel_grade.id}/composition', data={
            'carbon': '0.40',
            'manganese': '0.70',
            'silicon': '0.25',
            'chromium': '0.80',
            'nickel': '1.80',
            'molybdenum': '0.25',
            'vanadium': '0',
            'tungsten': '0',
            'copper': '0',
            'phosphorus': '0',
            'sulfur': '0',
            'nitrogen': '0',
            'boron': '0',
            'hollomon_jaffe_c': '18.5',
            'source': '',
            'notes': '',
        }, follow_redirects=True)
        assert rv.status_code == 200
        comp = SteelComposition.query.filter_by(
            steel_grade_id=sample_steel_grade.id).first()
        assert comp is not None
        assert comp.hollomon_jaffe_c == 18.5


class TestHistory:
    def test_renders(self, logged_in_client, sample_steel_grade):
        rv = logged_in_client.get(f'/materials/{sample_steel_grade.id}/history')
        assert rv.status_code == 200


class TestPropertyPlot:
    def test_constant_plot(self, logged_in_client, sample_steel_grade, db):
        prop = MaterialProperty(
            steel_grade_id=sample_steel_grade.id,
            property_name='density',
            property_type='constant',
            data=json.dumps({'value': 7850}),
        )
        db.session.add(prop)
        db.session.commit()
        rv = logged_in_client.get(
            f'/materials/{sample_steel_grade.id}/property/{prop.id}/plot')
        # Constant may not generate a plot — could be 200 or 404
        assert rv.status_code in (200, 404)

    def test_curve_plot(self, logged_in_client, sample_steel_grade, db):
        prop = MaterialProperty(
            steel_grade_id=sample_steel_grade.id,
            property_name='thermal_conductivity',
            property_type='curve',
            dependencies='temperature',
            data=json.dumps({'temperature': [20, 200, 400, 600], 'value': [46, 44, 40, 36]}),
        )
        db.session.add(prop)
        db.session.commit()
        rv = logged_in_client.get(
            f'/materials/{sample_steel_grade.id}/property/{prop.id}/plot')
        assert rv.status_code == 200

    def test_wrong_grade_404(self, logged_in_client, sample_steel_grade, db):
        rv = logged_in_client.get(f'/materials/99999/property/1/plot')
        assert rv.status_code == 404


class TestImportExport:
    def test_import_page(self, logged_in_client):
        rv = logged_in_client.get('/materials/import')
        assert rv.status_code == 200

    def test_export_single(self, logged_in_client, sample_steel_grade):
        rv = logged_in_client.get(f'/materials/{sample_steel_grade.id}/export')
        assert rv.status_code == 200

    def test_export_all(self, logged_in_client, sample_steel_grade):
        rv = logged_in_client.get('/materials/export-all')
        assert rv.status_code == 200

    def test_template_download(self, logged_in_client):
        rv = logged_in_client.get('/materials/template')
        assert rv.status_code == 200

    def test_export_404(self, logged_in_client):
        rv = logged_in_client.get('/materials/99999/export')
        assert rv.status_code == 404

    def test_requires_login(self, client, db):
        rv = client.get('/materials/import')
        assert rv.status_code == 302


class TestJominy:
    def test_requires_composition(self, logged_in_client, sample_steel_grade):
        rv = logged_in_client.get(f'/materials/{sample_steel_grade.id}/jominy')
        # Without composition, should still render (with message) or redirect
        assert rv.status_code in (200, 302)

    def test_with_composition(self, logged_in_client, sample_steel_grade, db):
        comp = SteelComposition(
            steel_grade_id=sample_steel_grade.id,
            carbon=0.40, manganese=0.70, silicon=0.25,
            chromium=0.80, nickel=1.80, molybdenum=0.25,
        )
        db.session.add(comp)
        db.session.commit()
        rv = logged_in_client.get(f'/materials/{sample_steel_grade.id}/jominy')
        assert rv.status_code == 200

    def test_curve_plot(self, logged_in_client, sample_steel_grade, db):
        comp = SteelComposition(
            steel_grade_id=sample_steel_grade.id,
            carbon=0.40, manganese=0.70, silicon=0.25,
            chromium=0.80, nickel=1.80, molybdenum=0.25,
        )
        db.session.add(comp)
        db.session.commit()
        rv = logged_in_client.get(f'/materials/{sample_steel_grade.id}/jominy/curve')
        assert rv.status_code == 200

    def test_phases_plot(self, logged_in_client, sample_steel_grade, db):
        comp = SteelComposition(
            steel_grade_id=sample_steel_grade.id,
            carbon=0.40, manganese=0.70, silicon=0.25,
            chromium=0.80, nickel=1.80, molybdenum=0.25,
        )
        db.session.add(comp)
        db.session.commit()
        rv = logged_in_client.get(f'/materials/{sample_steel_grade.id}/jominy/phases')
        assert rv.status_code == 200
