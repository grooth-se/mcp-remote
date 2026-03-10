from datetime import datetime
from app import db


class Customer(db.Model):
    __tablename__ = 'customers'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True, nullable=False)
    code = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    projects = db.relationship('Project', backref='customer', lazy='dynamic')

    def __repr__(self):
        return f'<Customer {self.name}>'


class Project(db.Model):
    __tablename__ = 'projects'

    id = db.Column(db.Integer, primary_key=True)
    project_number = db.Column(db.String(50), unique=True, nullable=False)
    project_name = db.Column(db.String(300))
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'))
    product_type = db.Column(db.String(50))  # TTR, SCR, CWOR, SLS, BODY, VALVE, FLANGE
    product_category = db.Column(db.String(50))  # Riser, Component
    materials = db.Column(db.JSON, default=list)  # List of material grades
    standards = db.Column(db.JSON, default=list)  # List of standards referenced
    folder_path = db.Column(db.String(500), nullable=False)
    indexed_at = db.Column(db.DateTime)
    metadata_ = db.Column('metadata', db.JSON, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    documents = db.relationship('Document', backref='project', lazy='dynamic')

    PRODUCT_TYPES = [
        ('TTR', 'Top Tensioned Riser'),
        ('SCR', 'Steel Catenary Riser'),
        ('CWOR', 'Coiled Tubing Work Over Riser'),
        ('SLS', 'Surface Landing String'),
        ('BODY', 'Bodies'),
        ('VALVE', 'Valves'),
        ('FLANGE', 'Flanges'),
    ]

    PRODUCT_CATEGORIES = {
        'TTR': 'Riser', 'SCR': 'Riser', 'CWOR': 'Riser', 'SLS': 'Riser',
        'BODY': 'Component', 'VALVE': 'Component', 'FLANGE': 'Component',
    }

    def __repr__(self):
        return f'<Project {self.project_number}>'
