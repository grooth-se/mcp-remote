"""Seed data for standard steel grades.

Contains 20 common steel grades with literature-based thermal properties.
Properties include temperature-dependent thermal conductivity and specific heat,
plus constant density and emissivity values.

Data sources:
- ASM Metals Handbook
- NIST Material Property Database
- Steel manufacturer datasheets
"""
from app.extensions import db
from app.models import (
    SteelGrade, MaterialProperty, PhaseDiagram, PhaseProperty,
    PROPERTY_TYPE_CONSTANT, PROPERTY_TYPE_CURVE,
    DATA_SOURCE_STANDARD, DIAGRAM_TYPE_CCT,
    PHASE_FERRITE, PHASE_AUSTENITE, PHASE_MARTENSITE, PHASE_BAINITE, PHASE_PEARLITE,
)


# Standard phase properties for low-alloy steel (typical values)
# Source: ASM Metals Handbook, various steel metallurgy references
STANDARD_PHASE_PROPERTIES = {
    PHASE_FERRITE: {
        'relative_density': 1.0000,  # Reference phase
        'thermal_expansion_coeff': 12.5e-6,  # 1/K (mean value 20-500°C)
    },
    PHASE_AUSTENITE: {
        'relative_density': 0.9800,  # ~2% volume expansion
        'thermal_expansion_coeff': 20.0e-6,  # Higher expansion (FCC structure)
    },
    PHASE_MARTENSITE: {
        'relative_density': 0.9780,  # ~2.2% volume expansion (depends on C content)
        'thermal_expansion_coeff': 11.0e-6,  # Similar to ferrite (BCT structure)
    },
    PHASE_BAINITE: {
        'relative_density': 0.9870,  # Between ferrite and martensite
        'thermal_expansion_coeff': 12.0e-6,
    },
    PHASE_PEARLITE: {
        'relative_density': 0.9980,  # Ferrite + cementite mix
        'thermal_expansion_coeff': 12.5e-6,
    },
}


# Standard steel grades with typical thermal properties
# Each entry: (designation, description, properties_dict, transformation_temps)
STANDARD_GRADES = [
    # Low alloy steels
    ('S355J2G3', 'Structural steel EN 10025', {
        'thermal_conductivity': {
            'type': 'curve',
            'units': 'W/(m·K)',
            'deps': 'temperature',
            'data': {'temperature': [20, 100, 200, 300, 400, 500, 600, 700, 800],
                     'value': [53, 51, 49, 46, 42, 38, 33, 28, 26]}
        },
        'specific_heat': {
            'type': 'curve',
            'units': 'J/(kg·K)',
            'deps': 'temperature',
            'data': {'temperature': [20, 100, 200, 300, 400, 500, 600, 700, 800],
                     'value': [450, 480, 510, 540, 580, 620, 700, 780, 650]}
        },
        'density': {'type': 'constant', 'units': 'kg/m³', 'data': {'value': 7850}},
        # Radiation properties
        'emissivity': {
            'type': 'curve',
            'units': '-',
            'deps': 'temperature',
            'data': {'temperature': [20, 200, 400, 600, 800, 1000],
                     'value': [0.25, 0.35, 0.50, 0.70, 0.85, 0.90]},
            'notes': 'Oxidized surface, increases with temperature'
        },
        'absorptivity': {'type': 'constant', 'units': '-', 'data': {'value': 0.85},
                        'notes': 'Thermal radiation absorptivity'},
        # Convection properties
        'htc_natural_convection': {
            'type': 'curve',
            'units': 'W/(m²·K)',
            'deps': 'temperature',
            'data': {'temperature': [20, 200, 400, 600, 800],
                     'value': [5, 8, 12, 18, 25]},
            'notes': 'Vertical plate in still air'
        },
        'surface_roughness': {'type': 'constant', 'units': 'µm', 'data': {'value': 3.2},
                             'notes': 'Typical machined surface Ra'},
    }, {'Ac1': 727, 'Ac3': 860, 'Ms': 420, 'Mf': 300}),

    ('AISI 4130', 'Chromium-molybdenum steel', {
        'thermal_conductivity': {
            'type': 'curve',
            'units': 'W/(m·K)',
            'deps': 'temperature',
            'data': {'temperature': [20, 100, 200, 300, 400, 500, 600, 700, 800],
                     'value': [42.7, 42.3, 40.5, 38.3, 35.7, 32.8, 29.7, 26.5, 25.8]}
        },
        'specific_heat': {
            'type': 'curve',
            'units': 'J/(kg·K)',
            'deps': 'temperature',
            'data': {'temperature': [20, 100, 200, 300, 400, 500, 600, 700, 800],
                     'value': [477, 502, 532, 565, 602, 644, 710, 790, 660]}
        },
        'density': {'type': 'constant', 'units': 'kg/m³', 'data': {'value': 7850}},
        'emissivity': {'type': 'constant', 'units': '-', 'data': {'value': 0.87}},
    }, {'Ac1': 745, 'Ac3': 810, 'Ms': 350, 'Mf': 200}),

    ('AISI 4340', 'Nickel-chromium-molybdenum steel', {
        'thermal_conductivity': {
            'type': 'curve',
            'units': 'W/(m·K)',
            'deps': 'temperature',
            'data': {'temperature': [20, 100, 200, 300, 400, 500, 600, 700, 800],
                     'value': [44.5, 44.0, 42.5, 40.2, 37.5, 34.5, 31.0, 27.5, 26.0]}
        },
        'specific_heat': {
            'type': 'curve',
            'units': 'J/(kg·K)',
            'deps': 'temperature',
            'data': {'temperature': [20, 100, 200, 300, 400, 500, 600, 700, 800],
                     'value': [475, 500, 530, 560, 600, 640, 700, 780, 650]}
        },
        'density': {'type': 'constant', 'units': 'kg/m³', 'data': {'value': 7850}},
        # Radiation properties - temperature dependent emissivity
        'emissivity': {
            'type': 'curve',
            'units': '-',
            'deps': 'temperature',
            'data': {'temperature': [20, 200, 400, 600, 800, 1000],
                     'value': [0.28, 0.38, 0.52, 0.72, 0.87, 0.92]},
            'notes': 'Total hemispherical emissivity, oxidized surface'
        },
        'absorptivity': {'type': 'constant', 'units': '-', 'data': {'value': 0.87}},
        # Convection properties
        'htc_natural_convection': {
            'type': 'curve',
            'units': 'W/(m²·K)',
            'deps': 'temperature',
            'data': {'temperature': [20, 200, 400, 600, 800],
                     'value': [5, 8, 12, 18, 25]},
            'notes': 'Natural convection in still air'
        },
        'htc_forced_convection': {
            'type': 'polynomial',
            'units': 'W/(m²·K)',
            'deps': 'temperature',
            'data': {'variable': 'temperature', 'coefficients': [20, 0.05, 0.00005]},
            'notes': 'Forced air, moderate velocity ~5 m/s'
        },
        'surface_roughness': {'type': 'constant', 'units': 'µm', 'data': {'value': 1.6},
                             'notes': 'Ground surface finish Ra'},
    }, {'Ac1': 724, 'Ac3': 780, 'Ms': 320, 'Mf': 180}),

    ('AISI 4330V', 'Vanadium-modified NiCrMo steel', {
        'thermal_conductivity': {
            'type': 'curve',
            'units': 'W/(m·K)',
            'deps': 'temperature',
            'data': {'temperature': [20, 100, 200, 300, 400, 500, 600, 700, 800],
                     'value': [41.9, 41.5, 40.0, 38.0, 35.5, 32.5, 29.5, 26.5, 25.5]}
        },
        'specific_heat': {
            'type': 'curve',
            'units': 'J/(kg·K)',
            'deps': 'temperature',
            'data': {'temperature': [20, 100, 200, 300, 400, 500, 600, 700, 800],
                     'value': [470, 495, 525, 555, 595, 635, 695, 775, 645]}
        },
        'density': {'type': 'constant', 'units': 'kg/m³', 'data': {'value': 7830}},
        'emissivity': {'type': 'constant', 'units': '-', 'data': {'value': 0.87}},
    }, {'Ac1': 730, 'Ac3': 790, 'Ms': 315, 'Mf': 175}),

    ('AISI 8630', 'Nickel-chromium-molybdenum steel', {
        'thermal_conductivity': {
            'type': 'curve',
            'units': 'W/(m·K)',
            'deps': 'temperature',
            'data': {'temperature': [20, 100, 200, 300, 400, 500, 600, 700, 800],
                     'value': [46.0, 45.5, 43.5, 41.0, 38.0, 35.0, 31.5, 28.0, 26.5]}
        },
        'specific_heat': {
            'type': 'curve',
            'units': 'J/(kg·K)',
            'deps': 'temperature',
            'data': {'temperature': [20, 100, 200, 300, 400, 500, 600, 700, 800],
                     'value': [460, 485, 515, 545, 585, 625, 685, 765, 640]}
        },
        'density': {'type': 'constant', 'units': 'kg/m³', 'data': {'value': 7850}},
        'emissivity': {'type': 'constant', 'units': '-', 'data': {'value': 0.86}},
    }, {'Ac1': 732, 'Ac3': 810, 'Ms': 370, 'Mf': 230}),

    # Pressure vessel steels
    ('A182 F22', 'CrMo pressure vessel steel (2.25Cr-1Mo)', {
        'thermal_conductivity': {
            'type': 'curve',
            'units': 'W/(m·K)',
            'deps': 'temperature',
            'data': {'temperature': [20, 100, 200, 300, 400, 500, 600, 700, 800],
                     'value': [37.7, 38.1, 37.5, 36.0, 33.8, 31.2, 28.5, 26.0, 25.5]}
        },
        'specific_heat': {
            'type': 'curve',
            'units': 'J/(kg·K)',
            'deps': 'temperature',
            'data': {'temperature': [20, 100, 200, 300, 400, 500, 600, 700, 800],
                     'value': [460, 490, 520, 550, 590, 635, 700, 780, 640]}
        },
        'density': {'type': 'constant', 'units': 'kg/m³', 'data': {'value': 7800}},
        'emissivity': {'type': 'constant', 'units': '-', 'data': {'value': 0.88}},
    }, {'Ac1': 790, 'Ac3': 865, 'Ms': 400, 'Mf': 260}),

    ('A182 F11', 'CrMo pressure vessel steel (1.25Cr-0.5Mo)', {
        'thermal_conductivity': {
            'type': 'curve',
            'units': 'W/(m·K)',
            'deps': 'temperature',
            'data': {'temperature': [20, 100, 200, 300, 400, 500, 600, 700, 800],
                     'value': [42.0, 42.5, 41.5, 39.5, 37.0, 34.0, 30.5, 27.5, 26.0]}
        },
        'specific_heat': {
            'type': 'curve',
            'units': 'J/(kg·K)',
            'deps': 'temperature',
            'data': {'temperature': [20, 100, 200, 300, 400, 500, 600, 700, 800],
                     'value': [465, 495, 525, 555, 595, 640, 705, 785, 650]}
        },
        'density': {'type': 'constant', 'units': 'kg/m³', 'data': {'value': 7850}},
        'emissivity': {'type': 'constant', 'units': '-', 'data': {'value': 0.87}},
    }, {'Ac1': 770, 'Ac3': 850, 'Ms': 410, 'Mf': 270}),

    ('A182 F5', 'CrMo pressure vessel steel (5Cr-0.5Mo)', {
        'thermal_conductivity': {
            'type': 'curve',
            'units': 'W/(m·K)',
            'deps': 'temperature',
            'data': {'temperature': [20, 100, 200, 300, 400, 500, 600, 700, 800],
                     'value': [35.0, 35.5, 35.0, 33.5, 31.5, 29.0, 26.5, 24.5, 24.0]}
        },
        'specific_heat': {
            'type': 'curve',
            'units': 'J/(kg·K)',
            'deps': 'temperature',
            'data': {'temperature': [20, 100, 200, 300, 400, 500, 600, 700, 800],
                     'value': [460, 485, 515, 545, 580, 620, 680, 760, 630]}
        },
        'density': {'type': 'constant', 'units': 'kg/m³', 'data': {'value': 7750}},
        'emissivity': {'type': 'constant', 'units': '-', 'data': {'value': 0.88}},
    }, {'Ac1': 820, 'Ac3': 880, 'Ms': 380, 'Mf': 240}),

    # Austenitic stainless steels
    ('304', 'Austenitic stainless steel (18Cr-8Ni)', {
        'thermal_conductivity': {
            'type': 'curve',
            'units': 'W/(m·K)',
            'deps': 'temperature',
            'data': {'temperature': [20, 100, 200, 300, 400, 500, 600, 700, 800],
                     'value': [16.2, 17.0, 18.5, 20.0, 21.5, 23.0, 24.5, 26.0, 27.5]}
        },
        'specific_heat': {
            'type': 'curve',
            'units': 'J/(kg·K)',
            'deps': 'temperature',
            'data': {'temperature': [20, 100, 200, 300, 400, 500, 600, 700, 800],
                     'value': [500, 510, 530, 545, 560, 575, 590, 605, 620]}
        },
        'density': {'type': 'constant', 'units': 'kg/m³', 'data': {'value': 8000}},
        'emissivity': {'type': 'constant', 'units': '-', 'data': {'value': 0.60}},
    }, None),  # No transformation for austenitic

    ('316', 'Austenitic stainless steel (16Cr-10Ni-2Mo)', {
        'thermal_conductivity': {
            'type': 'curve',
            'units': 'W/(m·K)',
            'deps': 'temperature',
            'data': {'temperature': [20, 100, 200, 300, 400, 500, 600, 700, 800],
                     'value': [14.6, 15.5, 17.0, 18.5, 20.0, 21.5, 23.0, 24.5, 26.0]}
        },
        'specific_heat': {
            'type': 'curve',
            'units': 'J/(kg·K)',
            'deps': 'temperature',
            'data': {'temperature': [20, 100, 200, 300, 400, 500, 600, 700, 800],
                     'value': [500, 510, 530, 545, 560, 575, 590, 605, 620]}
        },
        'density': {'type': 'constant', 'units': 'kg/m³', 'data': {'value': 8000}},
        'emissivity': {'type': 'constant', 'units': '-', 'data': {'value': 0.60}},
    }, None),

    ('316L', 'Low-carbon austenitic stainless steel', {
        'thermal_conductivity': {
            'type': 'curve',
            'units': 'W/(m·K)',
            'deps': 'temperature',
            'data': {'temperature': [20, 100, 200, 300, 400, 500, 600, 700, 800],
                     'value': [14.6, 15.5, 17.0, 18.5, 20.0, 21.5, 23.0, 24.5, 26.0]}
        },
        'specific_heat': {
            'type': 'curve',
            'units': 'J/(kg·K)',
            'deps': 'temperature',
            'data': {'temperature': [20, 100, 200, 300, 400, 500, 600, 700, 800],
                     'value': [500, 510, 530, 545, 560, 575, 590, 605, 620]}
        },
        'density': {'type': 'constant', 'units': 'kg/m³', 'data': {'value': 8000}},
        'emissivity': {'type': 'constant', 'units': '-', 'data': {'value': 0.60}},
    }, None),

    # Duplex stainless steels
    ('2205', 'Duplex stainless steel (22Cr-5Ni-3Mo)', {
        'thermal_conductivity': {
            'type': 'curve',
            'units': 'W/(m·K)',
            'deps': 'temperature',
            'data': {'temperature': [20, 100, 200, 300, 400, 500, 600],
                     'value': [15.0, 16.0, 17.5, 19.0, 20.5, 22.0, 23.5]}
        },
        'specific_heat': {
            'type': 'curve',
            'units': 'J/(kg·K)',
            'deps': 'temperature',
            'data': {'temperature': [20, 100, 200, 300, 400, 500, 600],
                     'value': [480, 500, 520, 540, 560, 580, 600]}
        },
        'density': {'type': 'constant', 'units': 'kg/m³', 'data': {'value': 7800}},
        'emissivity': {'type': 'constant', 'units': '-', 'data': {'value': 0.65}},
    }, None),

    ('2507', 'Super duplex stainless steel (25Cr-7Ni-4Mo)', {
        'thermal_conductivity': {
            'type': 'curve',
            'units': 'W/(m·K)',
            'deps': 'temperature',
            'data': {'temperature': [20, 100, 200, 300, 400, 500, 600],
                     'value': [14.0, 15.0, 16.5, 18.0, 19.5, 21.0, 22.5]}
        },
        'specific_heat': {
            'type': 'curve',
            'units': 'J/(kg·K)',
            'deps': 'temperature',
            'data': {'temperature': [20, 100, 200, 300, 400, 500, 600],
                     'value': [480, 500, 520, 540, 560, 580, 600]}
        },
        'density': {'type': 'constant', 'units': 'kg/m³', 'data': {'value': 7800}},
        'emissivity': {'type': 'constant', 'units': '-', 'data': {'value': 0.65}},
    }, None),

    # Martensitic stainless steel
    ('410', 'Martensitic stainless steel (13Cr)', {
        'thermal_conductivity': {
            'type': 'curve',
            'units': 'W/(m·K)',
            'deps': 'temperature',
            'data': {'temperature': [20, 100, 200, 300, 400, 500, 600, 700, 800],
                     'value': [24.9, 25.5, 26.5, 27.5, 28.5, 29.0, 29.5, 29.0, 28.5]}
        },
        'specific_heat': {
            'type': 'curve',
            'units': 'J/(kg·K)',
            'deps': 'temperature',
            'data': {'temperature': [20, 100, 200, 300, 400, 500, 600, 700, 800],
                     'value': [460, 480, 500, 520, 540, 560, 600, 680, 580]}
        },
        'density': {'type': 'constant', 'units': 'kg/m³', 'data': {'value': 7750}},
        'emissivity': {'type': 'constant', 'units': '-', 'data': {'value': 0.70}},
    }, {'Ac1': 800, 'Ac3': 870, 'Ms': 340, 'Mf': 200}),

    # Tool steels
    ('H13', 'Hot work tool steel (Cr-Mo-V)', {
        'thermal_conductivity': {
            'type': 'curve',
            'units': 'W/(m·K)',
            'deps': 'temperature',
            'data': {'temperature': [20, 100, 200, 300, 400, 500, 600, 700],
                     'value': [24.6, 25.5, 26.5, 27.5, 28.0, 28.5, 29.0, 29.0]}
        },
        'specific_heat': {
            'type': 'curve',
            'units': 'J/(kg·K)',
            'deps': 'temperature',
            'data': {'temperature': [20, 100, 200, 300, 400, 500, 600, 700],
                     'value': [460, 480, 500, 520, 540, 560, 580, 600]}
        },
        'density': {'type': 'constant', 'units': 'kg/m³', 'data': {'value': 7800}},
        'emissivity': {'type': 'constant', 'units': '-', 'data': {'value': 0.85}},
    }, {'Ac1': 870, 'Ac3': 1010, 'Ms': 320, 'Mf': 170}),

    ('P20', 'Plastic mold steel (Cr-Mn-Mo)', {
        'thermal_conductivity': {
            'type': 'curve',
            'units': 'W/(m·K)',
            'deps': 'temperature',
            'data': {'temperature': [20, 100, 200, 300, 400, 500, 600],
                     'value': [29.0, 30.0, 31.0, 31.5, 32.0, 32.0, 31.5]}
        },
        'specific_heat': {
            'type': 'curve',
            'units': 'J/(kg·K)',
            'deps': 'temperature',
            'data': {'temperature': [20, 100, 200, 300, 400, 500, 600],
                     'value': [460, 480, 510, 540, 570, 600, 640]}
        },
        'density': {'type': 'constant', 'units': 'kg/m³', 'data': {'value': 7850}},
        'emissivity': {'type': 'constant', 'units': '-', 'data': {'value': 0.85}},
    }, {'Ac1': 760, 'Ac3': 830, 'Ms': 350, 'Mf': 210}),

    # Ultra-high strength steel
    ('300M', 'Ultra-high strength steel (Si-Cr-Mo-V)', {
        'thermal_conductivity': {
            'type': 'curve',
            'units': 'W/(m·K)',
            'deps': 'temperature',
            'data': {'temperature': [20, 100, 200, 300, 400, 500, 600, 700, 800],
                     'value': [32.0, 33.0, 34.0, 34.5, 34.5, 34.0, 33.0, 31.5, 30.0]}
        },
        'specific_heat': {
            'type': 'curve',
            'units': 'J/(kg·K)',
            'deps': 'temperature',
            'data': {'temperature': [20, 100, 200, 300, 400, 500, 600, 700, 800],
                     'value': [475, 500, 530, 560, 600, 640, 700, 780, 650]}
        },
        'density': {'type': 'constant', 'units': 'kg/m³', 'data': {'value': 7830}},
        'emissivity': {'type': 'constant', 'units': '-', 'data': {'value': 0.87}},
    }, {'Ac1': 760, 'Ac3': 815, 'Ms': 285, 'Mf': 140}),

    # Nickel alloys
    ('Inconel 625', 'Nickel-chromium superalloy', {
        'thermal_conductivity': {
            'type': 'curve',
            'units': 'W/(m·K)',
            'deps': 'temperature',
            'data': {'temperature': [20, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000],
                     'value': [9.8, 10.8, 12.5, 14.1, 15.7, 17.5, 19.0, 20.8, 22.8, 25.2, 28.0]}
        },
        'specific_heat': {
            'type': 'curve',
            'units': 'J/(kg·K)',
            'deps': 'temperature',
            'data': {'temperature': [20, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000],
                     'value': [410, 427, 456, 481, 502, 523, 544, 565, 582, 603, 620]}
        },
        'density': {'type': 'constant', 'units': 'kg/m³', 'data': {'value': 8440}},
        'emissivity': {'type': 'constant', 'units': '-', 'data': {'value': 0.55}},
    }, None),  # No transformation for nickel alloys

    ('Inconel 718', 'Precipitation-hardening nickel alloy', {
        'thermal_conductivity': {
            'type': 'curve',
            'units': 'W/(m·K)',
            'deps': 'temperature',
            'data': {'temperature': [20, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000],
                     'value': [11.4, 12.5, 14.0, 15.5, 17.0, 18.5, 20.0, 21.5, 23.5, 25.5, 28.0]}
        },
        'specific_heat': {
            'type': 'curve',
            'units': 'J/(kg·K)',
            'deps': 'temperature',
            'data': {'temperature': [20, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000],
                     'value': [435, 450, 470, 490, 505, 520, 540, 565, 590, 620, 650]}
        },
        'density': {'type': 'constant', 'units': 'kg/m³', 'data': {'value': 8190}},
        'emissivity': {'type': 'constant', 'units': '-', 'data': {'value': 0.55}},
    }, None),

    # Carbon steel
    ('AISI 1045', 'Medium carbon steel', {
        'thermal_conductivity': {
            'type': 'curve',
            'units': 'W/(m·K)',
            'deps': 'temperature',
            'data': {'temperature': [20, 100, 200, 300, 400, 500, 600, 700, 800],
                     'value': [51.9, 51.0, 48.0, 44.0, 40.0, 36.0, 32.0, 28.0, 26.0]}
        },
        'specific_heat': {
            'type': 'curve',
            'units': 'J/(kg·K)',
            'deps': 'temperature',
            'data': {'temperature': [20, 100, 200, 300, 400, 500, 600, 700, 800],
                     'value': [486, 510, 540, 570, 610, 660, 730, 810, 670]}
        },
        'density': {'type': 'constant', 'units': 'kg/m³', 'data': {'value': 7850}},
        'emissivity': {'type': 'constant', 'units': '-', 'data': {'value': 0.85}},
    }, {'Ac1': 725, 'Ac3': 780, 'Ms': 355, 'Mf': 220}),
]


def seed_standard_grades() -> dict:
    """Seed the database with 20 standard steel grades.

    Returns
    -------
    dict
        Results with count of created items and any errors
    """
    results = {
        'grades_created': 0,
        'grades_skipped': 0,
        'properties_created': 0,
        'diagrams_created': 0,
        'phase_properties_created': 0,
        'errors': []
    }

    for designation, description, properties, transformation_temps in STANDARD_GRADES:
        # Check if grade already exists
        existing = SteelGrade.query.filter_by(
            designation=designation,
            data_source=DATA_SOURCE_STANDARD
        ).first()

        if existing:
            results['grades_skipped'] += 1
            continue

        try:
            # Create steel grade
            grade = SteelGrade(
                designation=designation,
                data_source=DATA_SOURCE_STANDARD,
                description=description
            )
            db.session.add(grade)
            db.session.flush()  # Get the ID
            results['grades_created'] += 1

            # Create properties
            for prop_name, prop_config in properties.items():
                prop = MaterialProperty(
                    steel_grade_id=grade.id,
                    property_name=prop_name,
                    property_type=prop_config['type'],
                    units=prop_config.get('units', ''),
                    dependencies=prop_config.get('deps', ''),
                )
                prop.set_data(prop_config['data'])
                db.session.add(prop)
                results['properties_created'] += 1

            # Create phase diagram if transformation temps provided
            if transformation_temps:
                diagram = PhaseDiagram(
                    steel_grade_id=grade.id,
                    diagram_type=DIAGRAM_TYPE_CCT
                )
                diagram.set_temps(transformation_temps)
                db.session.add(diagram)
                results['diagrams_created'] += 1

                # Also add standard phase properties for transformable steels
                for phase, phase_data in STANDARD_PHASE_PROPERTIES.items():
                    pp = PhaseProperty(
                        steel_grade_id=grade.id,
                        phase=phase,
                        relative_density=phase_data['relative_density'],
                        thermal_expansion_coeff=phase_data['thermal_expansion_coeff'],
                        expansion_type='constant',
                        reference_temperature=20.0,
                        notes='Standard literature values for low-alloy steel'
                    )
                    db.session.add(pp)
                    results['phase_properties_created'] += 1

        except Exception as e:
            results['errors'].append(f"Error creating {designation}: {str(e)}")

    db.session.commit()
    return results


def get_grade_by_designation(designation: str, data_source: str = DATA_SOURCE_STANDARD):
    """Get a steel grade by designation.

    Parameters
    ----------
    designation : str
        Steel grade designation
    data_source : str
        Data source (Standard or Subseatec)

    Returns
    -------
    SteelGrade or None
    """
    return SteelGrade.query.filter_by(
        designation=designation,
        data_source=data_source
    ).first()
