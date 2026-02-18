"""Tests for heat treatment templates blueprint routes."""
import json
import pytest
from app.models import HeatTreatmentTemplate, Simulation


class TestTemplateList:
    def test_renders(self, logged_in_client, sample_template):
        rv = logged_in_client.get('/templates/')
        assert rv.status_code == 200
        assert b'Standard Q' in rv.data

    def test_requires_login(self, client, db):
        rv = client.get('/templates/')
        assert rv.status_code == 302

    def test_public_visible(self, logged_in_client, db, admin_user):
        """Public template from another user is visible."""
        tmpl = HeatTreatmentTemplate(
            name='Public Template', user_id=admin_user.id,
            category='normalizing', is_public=True,
            heat_treatment_config=json.dumps({'quenching': {}}),
        )
        db.session.add(tmpl)
        db.session.commit()
        rv = logged_in_client.get('/templates/')
        assert b'Public Template' in rv.data

    def test_mine_filter(self, logged_in_client, sample_template):
        rv = logged_in_client.get('/templates/?mine=1')
        assert rv.status_code == 200

    def test_category_filter(self, logged_in_client, sample_template):
        rv = logged_in_client.get('/templates/?category=quench_temper')
        assert rv.status_code == 200


class TestTemplateCreate:
    def test_form_renders(self, logged_in_client):
        rv = logged_in_client.get('/templates/new')
        assert rv.status_code == 200

    def test_success(self, logged_in_client, db):
        rv = logged_in_client.post('/templates/new', data={
            'name': 'My Template',
            'description': 'Test template',
            'category': 'normalizing',
            'is_public': False,
        }, follow_redirects=True)
        assert rv.status_code == 200
        assert HeatTreatmentTemplate.query.filter_by(name='My Template').first() is not None

    def test_redirect_to_edit(self, logged_in_client, db):
        rv = logged_in_client.post('/templates/new', data={
            'name': 'Redirect Test',
            'description': '',
            'category': 'custom',
        })
        assert rv.status_code == 302

    def test_default_config(self, logged_in_client, db):
        logged_in_client.post('/templates/new', data={
            'name': 'Config Test',
            'description': '',
            'category': 'custom',
        })
        tmpl = HeatTreatmentTemplate.query.filter_by(name='Config Test').first()
        assert tmpl is not None
        config = tmpl.ht_config
        assert 'heating' in config
        assert 'quenching' in config

    def test_requires_login(self, client, db):
        rv = client.get('/templates/new')
        assert rv.status_code == 302


class TestTemplateView:
    def test_renders(self, logged_in_client, sample_template):
        rv = logged_in_client.get(f'/templates/{sample_template.id}')
        assert rv.status_code == 200

    def test_own_private(self, logged_in_client, db, engineer_user):
        tmpl = HeatTreatmentTemplate(
            name='Private', user_id=engineer_user.id,
            category='custom', is_public=False,
            heat_treatment_config='{}',
        )
        db.session.add(tmpl)
        db.session.commit()
        rv = logged_in_client.get(f'/templates/{tmpl.id}')
        assert rv.status_code == 200

    def test_public(self, logged_in_client, db, admin_user):
        tmpl = HeatTreatmentTemplate(
            name='Public', user_id=admin_user.id,
            category='custom', is_public=True,
            heat_treatment_config='{}',
        )
        db.session.add(tmpl)
        db.session.commit()
        rv = logged_in_client.get(f'/templates/{tmpl.id}')
        assert rv.status_code == 200

    def test_private_denied(self, logged_in_client, db, admin_user):
        tmpl = HeatTreatmentTemplate(
            name='Secret', user_id=admin_user.id,
            category='custom', is_public=False,
            heat_treatment_config='{}',
        )
        db.session.add(tmpl)
        db.session.commit()
        rv = logged_in_client.get(f'/templates/{tmpl.id}', follow_redirects=True)
        assert rv.status_code == 200  # Redirected to index

    def test_404(self, logged_in_client):
        rv = logged_in_client.get('/templates/99999')
        assert rv.status_code == 404


class TestTemplateEdit:
    def test_form_renders(self, logged_in_client, sample_template):
        rv = logged_in_client.get(f'/templates/{sample_template.id}/edit')
        assert rv.status_code == 200

    def test_updates(self, logged_in_client, sample_template, db):
        rv = logged_in_client.post(f'/templates/{sample_template.id}/edit', data={
            'name': 'Updated Name',
            'description': 'New desc',
            'category': 'annealing',
            'is_public': True,
        }, follow_redirects=True)
        assert rv.status_code == 200
        tmpl = db.session.get(HeatTreatmentTemplate, sample_template.id)
        assert tmpl.name == 'Updated Name'

    def test_owner_only(self, logged_in_client, db, admin_user):
        tmpl = HeatTreatmentTemplate(
            name='Admin Template', user_id=admin_user.id,
            category='custom', is_public=True,
            heat_treatment_config='{}',
        )
        db.session.add(tmpl)
        db.session.commit()
        rv = logged_in_client.get(f'/templates/{tmpl.id}/edit', follow_redirects=True)
        assert rv.status_code == 200  # Redirected

    def test_config_renders(self, logged_in_client, sample_template):
        rv = logged_in_client.get(f'/templates/{sample_template.id}/config')
        assert rv.status_code == 200

    def test_config_saves(self, logged_in_client, sample_template, db):
        rv = logged_in_client.post(f'/templates/{sample_template.id}/config', data={
            'heating_enabled': 'on',
            'heating_target_temperature': '900',
            'heating_hold_time': '30',
            'heating_initial_temperature': '25',
            'heating_furnace_atmosphere': 'air',
            'heating_furnace_htc': '25',
            'heating_furnace_emissivity': '0.85',
            'transfer_enabled': 'on',
            'transfer_duration': '15',
            'transfer_ambient_temperature': '25',
            'transfer_htc': '10',
            'transfer_emissivity': '0.85',
            'quenching_media': 'oil',
            'quenching_media_temperature': '60',
            'quenching_agitation': 'mild',
            'quenching_duration': '600',
            'tempering_temperature': '600',
            'tempering_hold_time': '90',
            'tempering_cooling_method': 'air',
            'tempering_htc': '25',
        }, follow_redirects=True)
        assert rv.status_code == 200
        tmpl = db.session.get(HeatTreatmentTemplate, sample_template.id)
        config = tmpl.ht_config
        assert config['quenching']['media'] == 'oil'


class TestTemplateDelete:
    def test_success(self, logged_in_client, sample_template, db):
        tid = sample_template.id
        rv = logged_in_client.post(f'/templates/{tid}/delete', follow_redirects=True)
        assert rv.status_code == 200
        assert db.session.get(HeatTreatmentTemplate, tid) is None

    def test_owner_only(self, logged_in_client, db, admin_user):
        tmpl = HeatTreatmentTemplate(
            name='Admin Only', user_id=admin_user.id,
            category='custom', is_public=True,
            heat_treatment_config='{}',
        )
        db.session.add(tmpl)
        db.session.commit()
        tid = tmpl.id
        rv = logged_in_client.post(f'/templates/{tid}/delete', follow_redirects=True)
        assert db.session.get(HeatTreatmentTemplate, tid) is not None

    def test_404(self, logged_in_client):
        rv = logged_in_client.post('/templates/99999/delete')
        assert rv.status_code == 404

    def test_redirects(self, logged_in_client, sample_template, db):
        rv = logged_in_client.post(f'/templates/{sample_template.id}/delete')
        assert rv.status_code == 302


class TestTemplateDuplicate:
    def test_success(self, logged_in_client, sample_template, db):
        rv = logged_in_client.post(
            f'/templates/{sample_template.id}/duplicate',
            follow_redirects=True)
        assert rv.status_code == 200
        copy = HeatTreatmentTemplate.query.filter(
            HeatTreatmentTemplate.name.contains('(Copy)')).first()
        assert copy is not None

    def test_public_ok(self, logged_in_client, db, admin_user):
        tmpl = HeatTreatmentTemplate(
            name='Public Dup', user_id=admin_user.id,
            category='custom', is_public=True,
            heat_treatment_config='{}',
        )
        db.session.add(tmpl)
        db.session.commit()
        rv = logged_in_client.post(f'/templates/{tmpl.id}/duplicate',
                                    follow_redirects=True)
        assert rv.status_code == 200

    def test_private_denied(self, logged_in_client, db, admin_user):
        tmpl = HeatTreatmentTemplate(
            name='Private Dup', user_id=admin_user.id,
            category='custom', is_public=False,
            heat_treatment_config='{}',
        )
        db.session.add(tmpl)
        db.session.commit()
        rv = logged_in_client.post(f'/templates/{tmpl.id}/duplicate',
                                    follow_redirects=True)
        assert rv.status_code == 200  # Redirected with flash

    def test_name_has_copy(self, logged_in_client, sample_template, db):
        logged_in_client.post(f'/templates/{sample_template.id}/duplicate')
        copy = HeatTreatmentTemplate.query.filter(
            HeatTreatmentTemplate.name.contains('(Copy)')).first()
        assert '(Copy)' in copy.name


class TestTemplateApply:
    def test_success(self, logged_in_client, sample_template, sample_simulation, db):
        rv = logged_in_client.post(
            f'/templates/{sample_template.id}/apply/{sample_simulation.id}',
            follow_redirects=True)
        assert rv.status_code == 200
        sim = db.session.get(Simulation, sample_simulation.id)
        assert sim.heat_treatment_config == sample_template.heat_treatment_config

    def test_increments_use_count(self, logged_in_client, sample_template, sample_simulation, db):
        before = sample_template.use_count or 0
        logged_in_client.post(
            f'/templates/{sample_template.id}/apply/{sample_simulation.id}')
        tmpl = db.session.get(HeatTreatmentTemplate, sample_template.id)
        assert tmpl.use_count == before + 1

    def test_access_denied_template(self, logged_in_client, sample_simulation, db, admin_user):
        tmpl = HeatTreatmentTemplate(
            name='Private T', user_id=admin_user.id,
            category='custom', is_public=False,
            heat_treatment_config='{}',
        )
        db.session.add(tmpl)
        db.session.commit()
        rv = logged_in_client.post(
            f'/templates/{tmpl.id}/apply/{sample_simulation.id}',
            follow_redirects=True)
        assert rv.status_code == 200  # Redirect

    def test_access_denied_sim(self, logged_in_client, sample_template, db, sample_steel_grade, admin_user):
        sim = Simulation(
            name='Other Sim', steel_grade_id=sample_steel_grade.id,
            user_id=admin_user.id, geometry_type='cylinder',
            process_type='quench_water', status='draft',
        )
        db.session.add(sim)
        db.session.commit()
        rv = logged_in_client.post(
            f'/templates/{sample_template.id}/apply/{sim.id}',
            follow_redirects=True)
        assert rv.status_code == 200  # Redirect


class TestTemplateAPI:
    def test_list_json(self, logged_in_client, sample_template):
        rv = logged_in_client.get('/templates/api/list')
        assert rv.status_code == 200
        data = rv.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_includes_public(self, logged_in_client, db, admin_user):
        tmpl = HeatTreatmentTemplate(
            name='API Public', user_id=admin_user.id,
            category='custom', is_public=True,
            heat_treatment_config='{}',
        )
        db.session.add(tmpl)
        db.session.commit()
        rv = logged_in_client.get('/templates/api/list')
        names = [t['name'] for t in rv.get_json()]
        assert 'API Public' in names

    def test_requires_login(self, client, db):
        rv = client.get('/templates/api/list')
        assert rv.status_code == 302

    def test_expected_fields(self, logged_in_client, sample_template):
        rv = logged_in_client.get('/templates/api/list')
        item = rv.get_json()[0]
        assert 'id' in item
        assert 'name' in item
        assert 'category' in item
        assert 'summary' in item
