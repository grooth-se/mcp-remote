from datetime import datetime
from app import db


class GenerationJob(db.Model):
    __tablename__ = 'generation_jobs'

    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(db.String(20), default='pending')  # pending, processing, review, completed, failed
    template_id = db.Column(db.Integer, db.ForeignKey('templates.id'), nullable=True)

    # Input
    new_project_name = db.Column(db.String(300))
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True)
    product_type = db.Column(db.String(50))
    uploaded_documents = db.Column(db.JSON, default=list)
    extracted_requirements = db.Column(db.JSON, default=dict)

    # Similarity
    similar_projects = db.Column(db.JSON, default=list)
    selected_references = db.Column(db.JSON, default=list)

    # Output
    generated_document_path = db.Column(db.String(500))
    generation_log = db.Column(db.Text)

    # Chat refinement
    chat_history = db.Column(db.JSON, default=list)
    current_version = db.Column(db.Integer, default=1)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    template = db.relationship('Template', backref='generation_jobs')
    customer = db.relationship('Customer', backref='generation_jobs')
    versions = db.relationship('DocumentVersion', backref='generation_job', lazy='dynamic',
                               order_by='DocumentVersion.version_number')

    STATUS_LABELS = {
        'pending': 'Pending',
        'extracting': 'Extracting Text',
        'analyzing': 'Analyzing Requirements',
        'matching': 'Finding Similar Projects',
        'review': 'Awaiting Review',
        'generating': 'Generating Document',
        'completed': 'Completed',
        'failed': 'Failed',
    }

    @property
    def status_label(self):
        return self.STATUS_LABELS.get(self.status, self.status.title())

    def __repr__(self):
        return f'<GenerationJob {self.id} ({self.status})>'


class DocumentVersion(db.Model):
    __tablename__ = 'document_versions'

    id = db.Column(db.Integer, primary_key=True)
    generation_job_id = db.Column(db.Integer, db.ForeignKey('generation_jobs.id'), nullable=False)
    version_number = db.Column(db.Integer, nullable=False)
    file_path = db.Column(db.String(500))
    changes_description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<DocumentVersion {self.generation_job_id}v{self.version_number}>'
