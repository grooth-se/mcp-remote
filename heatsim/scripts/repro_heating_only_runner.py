"""Reproduce the user's error by driving the full simulation runner with
a heating-only HT config. Prints the traceback (if any) and the final
sim.error_message.
"""

from __future__ import annotations

import json
import os
import sys
import traceback

os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")
os.environ.setdefault("FLASK_CONFIG", "testing")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models import Simulation, SteelGrade, User
from app.models.material import DATA_SOURCE_STANDARD, MaterialProperty, SteelComposition
from app.models.simulation import (
    GEOMETRY_CYLINDER,
    PROCESS_QUENCH_WATER,
    STATUS_DRAFT,
)


def seed_grade(session):
    import uuid

    grade = SteelGrade(
        designation=f"REPRO-{uuid.uuid4().hex[:8]}", data_source=DATA_SOURCE_STANDARD
    )
    session.add(grade)
    session.flush()

    # Add a composition so phase prediction / hardness can engage.
    comp = SteelComposition(
        steel_grade_id=grade.id,
        carbon=0.40,
        manganese=0.70,
        silicon=0.25,
        chromium=0.80,
        nickel=1.80,
        molybdenum=0.25,
    )
    session.add(comp)

    for name, units, val in (
        ("thermal_conductivity", "W/(m·K)", 40.0),
        ("specific_heat", "J/(kg·K)", 500.0),
        ("density", "kg/m^3", 7850.0),
        ("emissivity", "-", 0.85),
    ):
        prop = MaterialProperty(
            steel_grade_id=grade.id,
            property_name=name,
            property_type="constant",
            units=units,
            data=json.dumps({"value": val}),
        )
        session.add(prop)

    session.commit()
    return grade


def heating_only_ht():
    return {
        "heating": {
            "enabled": True,
            "initial_temperature": 25.0,
            "target_temperature": 850.0,
            "hold_time": 30.0,
            "furnace_htc": 25.0,
            "furnace_emissivity": 0.85,
            "use_radiation": True,
            "end_condition": "equilibrium",
        },
        "transfer": {"enabled": False},
        "quenching": {"enabled": False},
        "tempering": {"enabled": False},
    }


def main() -> int:
    app = create_app("testing")
    with app.app_context():
        user = User(username="repro", role="engineer")
        user.set_password("x")
        db.session.add(user)
        db.session.commit()

        grade = seed_grade(db.session)

        sim = Simulation(
            name="heating-only repro",
            description="Reproduce phase-properties error",
            steel_grade_id=grade.id,
            user_id=user.id,
            geometry_type=GEOMETRY_CYLINDER,
            process_type=PROCESS_QUENCH_WATER,
            status=STATUS_DRAFT,
        )
        sim.set_geometry({"radius": 0.025, "length": 0.1})
        sim.set_solver_config(
            {"n_nodes": 21, "dt": 1.0, "max_time": 7200, "solver_type": "builtin"}
        )
        sim.set_ht_config(heating_only_ht())
        db.session.add(sim)
        db.session.commit()

        from app.services.simulation_runner import run_heat_treatment

        try:
            run_heat_treatment(sim.id)
        except Exception:
            print("--- Unhandled exception escaped run_heat_treatment ---")
            traceback.print_exc()

        db.session.refresh(sim)
        print("\n--- Final sim state ---")
        print(f"  status        : {sim.status}")
        print(f"  error_message : {sim.error_message!r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
