"""Extractors for project data."""

import pandas as pd
from app.extractors.base import BaseExtractor
from app.models.projects import (
    Project, ProjectAdjustment, TimeTracking, CustomerOrderProjectMap
)


class ProjectExtractor(BaseExtractor):
    """Import project follow-up from projektuppf.xlsx."""

    model_class = Project
    mapping_key = 'projektuppf'

    def clean_dataframe(self, df):
        df = super().clean_dataframe(df)

        # Convert dates
        for col in ['start_date', 'end_date']:
            df[col] = pd.to_datetime(df[col], errors='coerce').dt.date

        # Ensure numeric fields
        for col in ['executed_cost', 'executed_income', 'expected_cost',
                     'expected_income', 'remaining_cost', 'remaining_income']:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        # Ensure project_number is string
        df['project_number'] = df['project_number'].apply(
            lambda x: str(x) if x is not None else None
        )

        return df


class ProjectAdjustmentExtractor(BaseExtractor):
    """Import project adjustments from projectadjustments.xlsx."""

    model_class = ProjectAdjustment
    mapping_key = 'projectadjustments'

    def clean_dataframe(self, df):
        df = super().clean_dataframe(df)

        df['include_in_accrued'] = df['include_in_accrued'].apply(
            lambda x: bool(x) if x is not None else True
        )

        for col in ['contingency', 'income_adjustment',
                     'cost_calc_adjustment', 'purchase_adjustment']:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        df['project_number'] = df['project_number'].apply(
            lambda x: str(x) if x is not None else None
        )
        df['closing_date'] = df['closing_date'].apply(
            lambda x: str(x) if x is not None else None
        )

        return df


class TimeTrackingExtractor(BaseExtractor):
    """Import time tracking from tiduppfoljning.xlsx."""

    model_class = TimeTracking
    mapping_key = 'tiduppfoljning'

    def clean_dataframe(self, df):
        df = super().clean_dataframe(df)

        for col in ['planned_time', 'actual_hours', 'expected_hours', 'remaining']:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        df['project_number'] = df['project_number'].apply(
            lambda x: str(x) if x is not None else None
        )

        return df


class CrossRefExtractor(BaseExtractor):
    """Import order-project cross-reference from CO_proj_crossref.xlsx."""

    model_class = CustomerOrderProjectMap
    mapping_key = 'CO_proj_crossref'

    def clean_dataframe(self, df):
        df = super().clean_dataframe(df)

        df['order_number'] = pd.to_numeric(
            df['order_number'], errors='coerce'
        ).astype('Int64')
        df['order_number'] = df['order_number'].apply(
            lambda x: int(x) if x is not None and pd.notna(x) else None
        )

        df['project_number'] = df['project_number'].apply(
            lambda x: str(x) if x is not None else None
        )

        return df
