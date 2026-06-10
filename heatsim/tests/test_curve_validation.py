"""Unit tests for curve property data validation/normalization."""

import json

from app.services.curve_validation import parse_curve_data


class TestParseCurveData:
    def test_valid_json_string(self):
        raw = json.dumps({"temperature": [20, 200, 400], "value": [50, 45, 40]})
        data, errors = parse_curve_data(raw)
        assert errors == []
        assert data == {"temperature": [20.0, 200.0, 400.0], "value": [50.0, 45.0, 40.0]}

    def test_valid_dict_input(self):
        data, errors = parse_curve_data({"temperature": [0, 100], "value": [1, 2]})
        assert errors == []
        assert data["temperature"] == [0.0, 100.0]

    def test_quoted_numbers_coerced(self):
        raw = json.dumps({"temperature": ["20", "200"], "value": ["50", "45"]})
        data, errors = parse_curve_data(raw)
        assert errors == []
        assert data == {"temperature": [20.0, 200.0], "value": [50.0, 45.0]}

    def test_decimal_comma_coerced(self):
        raw = json.dumps({"temperature": ["20,5", "200"], "value": ["45,5", "40"]})
        data, errors = parse_curve_data(raw)
        assert errors == []
        assert data["temperature"][0] == 20.5
        assert data["value"][0] == 45.5

    def test_unsorted_input_sorted_by_temperature(self):
        raw = json.dumps({"temperature": [400, 20, 200], "value": [40, 50, 45]})
        data, errors = parse_curve_data(raw)
        assert errors == []
        assert data["temperature"] == [20.0, 200.0, 400.0]
        assert data["value"] == [50.0, 45.0, 40.0]

    def test_unequal_lengths_rejected(self):
        raw = json.dumps({"temperature": [20, 200, 400], "value": [50, 45]})
        data, errors = parse_curve_data(raw)
        assert data is None
        assert any("different lengths" in e for e in errors)

    def test_fewer_than_two_points_rejected(self):
        data, errors = parse_curve_data({"temperature": [20], "value": [50]})
        assert data is None
        assert any("at least 2" in e for e in errors)

    def test_garbage_values_reported_with_row(self):
        raw = json.dumps({"temperature": [20, "hot"], "value": [50, 45]})
        data, errors = parse_curve_data(raw)
        assert data is None
        assert any("Row 2" in e for e in errors)

    def test_invalid_json_rejected(self):
        data, errors = parse_curve_data("{not json")
        assert data is None
        assert any("not valid JSON" in e for e in errors)

    def test_empty_string_rejected(self):
        data, errors = parse_curve_data("   ")
        assert data is None
        assert errors

    def test_missing_keys_rejected(self):
        data, errors = parse_curve_data(json.dumps({"temp": [1, 2]}))
        assert data is None
        assert errors

    def test_json_list_rejected(self):
        data, errors = parse_curve_data(json.dumps([1, 2, 3]))
        assert data is None
        assert errors

    def test_duplicate_temperatures_rejected(self):
        data, errors = parse_curve_data({"temperature": [20, 20, 400], "value": [1, 2, 3]})
        assert data is None
        assert any("Duplicate" in e for e in errors)

    def test_nan_rejected(self):
        data, errors = parse_curve_data({"temperature": [20, "nan"], "value": [1, 2]})
        assert data is None

    def test_booleans_rejected(self):
        data, errors = parse_curve_data({"temperature": [True, 20], "value": [1, 2]})
        assert data is None


class TestEvaluateScalar:
    """evaluate_scalar must reduce any property type to a usable number."""

    def _prop(self, db, grade, name, ptype, data):
        from app.models import MaterialProperty

        prop = MaterialProperty(
            steel_grade_id=grade.id, property_name=name, property_type=ptype
        )
        prop.set_data(data)
        db.session.add(prop)
        db.session.commit()
        return prop

    def test_none_returns_default(self):
        from app.services.property_evaluator import evaluate_scalar

        assert evaluate_scalar(None, 7850.0) == 7850.0

    def test_constant(self, db, sample_steel_grade):
        from app.services.property_evaluator import evaluate_scalar

        prop = self._prop(db, sample_steel_grade, "density", "constant", {"value": 7700})
        assert evaluate_scalar(prop, 7850.0) == 7700.0

    def test_curve_evaluated_at_reference_temperature(self, db, sample_steel_grade):
        from app.services.property_evaluator import evaluate_scalar

        prop = self._prop(
            db,
            sample_steel_grade,
            "emissivity",
            "curve",
            {"temperature": [0.0, 1000.0], "value": [0.2, 0.8]},
        )
        assert evaluate_scalar(prop, 0.85, temperature=500.0) == 0.5

    def test_curve_density_does_not_crash(self, db, sample_steel_grade):
        """A curve-type density used to leak a list into the solver."""
        from app.services.property_evaluator import evaluate_scalar

        prop = self._prop(
            db,
            sample_steel_grade,
            "density",
            "curve",
            {"temperature": [20.0, 800.0], "value": [7850.0, 7600.0]},
        )
        result = evaluate_scalar(prop, 7850.0, temperature=20.0)
        assert isinstance(result, float)
        assert result == 7850.0

    def test_garbage_data_returns_default(self, db, sample_steel_grade):
        from app.services.property_evaluator import evaluate_scalar

        prop = self._prop(db, sample_steel_grade, "density", "constant", {"value": "junk!"})
        assert evaluate_scalar(prop, 7850.0) == 7850.0
