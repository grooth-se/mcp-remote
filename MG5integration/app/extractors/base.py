"""Base extractor with shared Excel import logic."""

import pandas as pd
import numpy as np
from app.extensions import db


class BaseExtractor:
    """Base class for all data extractors."""

    model_class = None  # Override in subclass
    mapping_key = None  # Key into COLUMN_MAPPINGS
    batch_size = 5000

    def get_column_mapping(self):
        """Return the Swedish->English column mapping for this extractor."""
        from app.utils.excel_analyzer import COLUMN_MAPPINGS
        return COLUMN_MAPPINGS.get(self.mapping_key, {})

    def read_excel(self, filepath):
        """Read Excel file and rename columns using mapping.

        Returns a DataFrame with English column names.
        """
        df = pd.read_excel(filepath)
        mapping = self.get_column_mapping()
        df = df.rename(columns=mapping)

        # Drop any columns not in the mapping (keep only mapped columns)
        known_cols = set(mapping.values())
        cols_to_keep = [c for c in df.columns if c in known_cols]
        df = df[cols_to_keep]

        return df

    def clean_dataframe(self, df):
        """Clean common data issues. Override for domain-specific cleaning."""
        # Replace NaN with None for nullable fields
        df = df.replace({np.nan: None})

        # Strip whitespace from string columns
        for col in df.select_dtypes(include=['object']).columns:
            df[col] = df[col].apply(
                lambda x: x.strip() if isinstance(x, str) else x
            )

        return df

    def dataframe_to_records(self, df):
        """Convert DataFrame to list of dicts suitable for bulk insert.

        Ensures NaN/NaT values are converted to None for SQLAlchemy.
        """
        records = df.to_dict('records')
        for rec in records:
            for key, val in rec.items():
                if val is pd.NaT or (isinstance(val, float) and np.isnan(val)):
                    rec[key] = None
        return records

    def clear_data(self):
        """Remove all data for this model (full refresh)."""
        self.model_class.query.delete()
        db.session.commit()

    def bulk_insert(self, records):
        """Insert records in batches."""
        total = 0
        for i in range(0, len(records), self.batch_size):
            batch = records[i:i + self.batch_size]
            db.session.bulk_insert_mappings(self.model_class, batch)
            db.session.commit()
            total += len(batch)
        return total

    def extract_from_excel(self, filepath, batch_id=None):
        """Full extraction pipeline: read -> clean -> clear -> insert.

        Returns number of records imported.
        """
        df = self.read_excel(filepath)
        df = self.clean_dataframe(df)
        records = self.dataframe_to_records(df)

        # Add batch_id to all records
        if batch_id:
            for rec in records:
                rec['import_batch_id'] = batch_id
                rec['source'] = 'excel'

        self.clear_data()
        count = self.bulk_insert(records)
        return count
