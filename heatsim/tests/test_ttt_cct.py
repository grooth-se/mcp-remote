"""Integration tests for TTT/CCT blueprint routes."""
import pytest

from app.extensions import db as _db
from app.models import SteelGrade, DATA_SOURCE_STANDARD
from app.models.material import SteelComposition
from app.models.ttt_parameters import (
    TTTParameters, JMAKParameters, MartensiteParameters,
    B_MODEL_GAUSSIAN,
)


@pytest.fixture()
def grade_with_comp(db):
    """Steel grade with composition (AISI 4340)."""
    grade = SteelGrade(designation='AISI 4340', data_source=DATA_SOURCE_STANDARD)
    db.session.add(grade)
    db.session.flush()

    comp = SteelComposition(
        steel_grade_id=grade.id,
        carbon=0.40, manganese=0.70, silicon=0.25,
        chromium=0.80, nickel=1.80, molybdenum=0.25,
    )
    db.session.add(comp)
    db.session.commit()
    return grade


@pytest.fixture()
def grade_with_ttt(grade_with_comp, db):
    """Steel grade with TTT parameters and JMAK data."""
    grade = grade_with_comp
    ttt = TTTParameters(
        steel_grade_id=grade.id,
        ae1=727, ae3=840, bs=550, ms=320, mf=120,
        data_source='empirical',
    )
    db.session.add(ttt)
    db.session.flush()

    # Add pearlite JMAK
    jmak_p = JMAKParameters(
        ttt_parameters_id=ttt.id,
        phase='pearlite',
        n_value=1.5,
        b_model_type=B_MODEL_GAUSSIAN,
        nose_temperature=650,
        nose_time=3.0,
        temp_range_min=400,
        temp_range_max=727,
    )
    jmak_p.set_b_params({'b_max': 0.001, 't_nose': 650, 'sigma': 60})
    db.session.add(jmak_p)

    # Add bainite JMAK
    jmak_b = JMAKParameters(
        ttt_parameters_id=ttt.id,
        phase='bainite',
        n_value=2.5,
        b_model_type=B_MODEL_GAUSSIAN,
        nose_temperature=450,
        nose_time=0.5,
        temp_range_min=250,
        temp_range_max=550,
    )
    jmak_b.set_b_params({'b_max': 0.005, 't_nose': 450, 'sigma': 50})
    db.session.add(jmak_b)

    # Add martensite params
    mart = MartensiteParameters(
        ttt_parameters_id=ttt.id,
        ms=320, mf=120, alpha_m=0.011,
    )
    db.session.add(mart)

    db.session.commit()
    return grade


# === Index Route ===

class TestIndex:
    def test_index_requires_login(self, client):
        resp = client.get('/ttt-cct/')
        assert resp.status_code in (302, 401)

    def test_index_lists_grades(self, logged_in_client, grade_with_comp):
        resp = logged_in_client.get('/ttt-cct/')
        assert resp.status_code == 200
        assert b'AISI 4340' in resp.data


# === View Route ===

class TestView:
    def test_view_requires_login(self, client, grade_with_comp):
        resp = client.get(f'/ttt-cct/grade/{grade_with_comp.id}')
        assert resp.status_code in (302, 401)

    def test_view_shows_grade(self, logged_in_client, grade_with_comp):
        resp = logged_in_client.get(f'/ttt-cct/grade/{grade_with_comp.id}')
        assert resp.status_code == 200
        assert b'AISI 4340' in resp.data

    def test_view_shows_jmak_data(self, logged_in_client, grade_with_ttt):
        resp = logged_in_client.get(f'/ttt-cct/grade/{grade_with_ttt.id}')
        assert resp.status_code == 200
        assert b'Pearlite' in resp.data or b'pearlite' in resp.data

    def test_view_shows_martensite(self, logged_in_client, grade_with_ttt):
        resp = logged_in_client.get(f'/ttt-cct/grade/{grade_with_ttt.id}')
        assert resp.status_code == 200
        assert b'320' in resp.data  # Ms temperature

    def test_view_404_for_missing_grade(self, logged_in_client):
        resp = logged_in_client.get('/ttt-cct/grade/99999')
        assert resp.status_code == 404


# === Edit Parameters ===

class TestEditParameters:
    def test_edit_parameters_get(self, logged_in_client, grade_with_comp):
        resp = logged_in_client.get(f'/ttt-cct/grade/{grade_with_comp.id}/edit')
        assert resp.status_code == 200
        assert b'Transformation Temperatures' in resp.data

    def test_edit_parameters_post(self, logged_in_client, grade_with_comp, db):
        resp = logged_in_client.post(
            f'/ttt-cct/grade/{grade_with_comp.id}/edit',
            data={
                'ae1': 727, 'ae3': 840, 'bs': 550, 'ms': 320, 'mf': 120,
                'austenitizing_temperature': 850,
                'grain_size_astm': 8,
                'data_source': 'empirical',
                'notes': 'Test',
                'submit': 'Save',
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200

        ttt = TTTParameters.query.filter_by(steel_grade_id=grade_with_comp.id).first()
        assert ttt is not None
        assert ttt.ae1 == 727
        assert ttt.ms == 320


# === Edit JMAK ===

class TestEditJMAK:
    def test_edit_jmak_redirects_without_ttt(self, logged_in_client, grade_with_comp):
        resp = logged_in_client.get(
            f'/ttt-cct/grade/{grade_with_comp.id}/jmak/pearlite',
            follow_redirects=True,
        )
        assert resp.status_code == 200
        # Should flash warning about creating TTT params first
        assert b'Create TTT parameters first' in resp.data or b'edit' in resp.data.lower()

    def test_edit_jmak_get(self, logged_in_client, grade_with_ttt):
        resp = logged_in_client.get(
            f'/ttt-cct/grade/{grade_with_ttt.id}/jmak/pearlite'
        )
        assert resp.status_code == 200
        assert b'JMAK Parameters' in resp.data

    def test_edit_jmak_post(self, logged_in_client, grade_with_ttt, db):
        resp = logged_in_client.post(
            f'/ttt-cct/grade/{grade_with_ttt.id}/jmak/ferrite',
            data={
                'phase': 'ferrite',
                'n_value': 2.0,
                'b_model_type': 'gaussian',
                'b_max': 0.002,
                't_nose': 700,
                'sigma': 50,
                'nose_temperature': 700,
                'nose_time': 1.5,
                'temp_range_min': 550,
                'temp_range_max': 840,
                'submit': 'Save',
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200

        ttt = TTTParameters.query.filter_by(steel_grade_id=grade_with_ttt.id).first()
        jmak = ttt.jmak_parameters.filter_by(phase='ferrite').first()
        assert jmak is not None
        assert jmak.n_value == 2.0


# === Edit Martensite ===

class TestEditMartensite:
    def test_edit_martensite_get(self, logged_in_client, grade_with_ttt):
        resp = logged_in_client.get(
            f'/ttt-cct/grade/{grade_with_ttt.id}/martensite'
        )
        assert resp.status_code == 200
        assert b'Koistinen-Marburger' in resp.data

    def test_edit_martensite_post(self, logged_in_client, grade_with_ttt, db):
        resp = logged_in_client.post(
            f'/ttt-cct/grade/{grade_with_ttt.id}/martensite',
            data={
                'ms': 330, 'mf': 130, 'alpha_m': 0.015,
                'submit': 'Save',
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200

        ttt = TTTParameters.query.filter_by(steel_grade_id=grade_with_ttt.id).first()
        assert ttt.martensite_parameters.ms == 330


# === Auto-Generate ===

class TestAutoGenerate:
    def test_auto_generate_creates_params(self, logged_in_client, grade_with_comp, db):
        resp = logged_in_client.post(
            f'/ttt-cct/grade/{grade_with_comp.id}/auto-generate',
            follow_redirects=True,
        )
        assert resp.status_code == 200

        ttt = TTTParameters.query.filter_by(steel_grade_id=grade_with_comp.id).first()
        assert ttt is not None
        assert ttt.ae1 is not None
        assert ttt.ms is not None
        assert ttt.data_source == 'empirical'

        # Should have JMAK data
        assert ttt.jmak_parameters.count() > 0

        # Should have martensite
        assert ttt.martensite_parameters is not None

    def test_auto_generate_without_composition(self, logged_in_client, db):
        grade = SteelGrade(designation='NoComp', data_source=DATA_SOURCE_STANDARD)
        db.session.add(grade)
        db.session.commit()

        resp = logged_in_client.post(
            f'/ttt-cct/grade/{grade.id}/auto-generate',
            follow_redirects=True,
        )
        assert resp.status_code == 200
        # Should flash warning
        assert b'composition required' in resp.data.lower() or b'composition' in resp.data.lower()


# === Plot Routes ===

class TestPlotRoutes:
    def test_ttt_plot_with_data(self, logged_in_client, grade_with_ttt):
        resp = logged_in_client.get(f'/ttt-cct/grade/{grade_with_ttt.id}/ttt-plot')
        # Should return PNG image
        assert resp.status_code == 200
        assert resp.content_type == 'image/png'
        assert len(resp.data) > 100  # Should be a real image

    def test_ttt_plot_without_data(self, logged_in_client, grade_with_comp):
        resp = logged_in_client.get(f'/ttt-cct/grade/{grade_with_comp.id}/ttt-plot')
        assert resp.status_code == 404

    def test_cct_plot_with_data(self, logged_in_client, grade_with_ttt):
        resp = logged_in_client.get(f'/ttt-cct/grade/{grade_with_ttt.id}/cct-plot')
        assert resp.status_code == 200
        assert resp.content_type == 'image/png'

    def test_cct_plot_without_data(self, logged_in_client, grade_with_comp):
        resp = logged_in_client.get(f'/ttt-cct/grade/{grade_with_comp.id}/cct-plot')
        # Should either return 404 or fall back to empirical curves
        assert resp.status_code in (200, 404)


# === API Routes ===

class TestAPIRoutes:
    def test_ttt_data_json(self, logged_in_client, grade_with_ttt):
        resp = logged_in_client.get(f'/ttt-cct/api/grade/{grade_with_ttt.id}/ttt-data')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'curves' in data
        assert 'tier' in data

    def test_cct_data_json(self, logged_in_client, grade_with_ttt):
        resp = logged_in_client.get(f'/ttt-cct/api/grade/{grade_with_ttt.id}/cct-data')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'curves' in data
        assert 'tier' in data


# === Phase Predictor Integration ===

class TestPhasePredictor:
    def test_predictor_tier_with_jmak(self, app, grade_with_ttt):
        with app.app_context():
            from app.services.phase_transformation import PhasePredictor
            predictor = PhasePredictor(grade_with_ttt)
            assert predictor.is_available
            assert predictor.tier == 'jmak'

    def test_predictor_tier_empirical(self, app, grade_with_comp):
        with app.app_context():
            from app.services.phase_transformation import PhasePredictor
            predictor = PhasePredictor(grade_with_comp)
            # Should fall back to empirical (has composition but no JMAK)
            assert predictor.tier in ('empirical', 'none')

    def test_predictor_get_transformation_temps(self, app, grade_with_ttt):
        with app.app_context():
            from app.services.phase_transformation import PhasePredictor
            predictor = PhasePredictor(grade_with_ttt)
            temps = predictor.get_transformation_temps()
            assert temps.get('Ms') == 320
            assert temps.get('Ae1') == 727

    def test_predictor_get_cct_curves(self, app, grade_with_ttt):
        with app.app_context():
            from app.services.phase_transformation import PhasePredictor
            predictor = PhasePredictor(grade_with_ttt)
            curves = predictor.get_cct_curves()
            assert curves is not None
            assert len(curves) > 0

    def test_predictor_get_ttt_curves(self, app, grade_with_ttt):
        with app.app_context():
            from app.services.phase_transformation import PhasePredictor
            predictor = PhasePredictor(grade_with_ttt)
            curves = predictor.get_ttt_curves()
            assert curves is not None
            assert len(curves) > 0
