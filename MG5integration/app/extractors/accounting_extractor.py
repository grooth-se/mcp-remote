"""Extractors for accounting data: Chart of Accounts and Verifications."""

import pandas as pd
from app.extractors.base import BaseExtractor
from app.models.accounting import Account, Verification


class AccountExtractor(BaseExtractor):
    """Import chart of accounts from kontoplan.xlsx."""

    model_class = Account
    mapping_key = 'kontoplan'

    def clean_dataframe(self, df):
        df = super().clean_dataframe(df)
        # Ensure account_number is integer
        df['account_number'] = pd.to_numeric(
            df['account_number'], errors='coerce'
        ).astype('Int64')
        # Drop rows without account number
        df = df.dropna(subset=['account_number'])
        df['account_number'] = df['account_number'].astype(int)
        # SRU code as string (handle NaN properly)
        df['sru_code'] = df['sru_code'].apply(
            lambda x: str(int(x)) if x is not None and isinstance(x, (int, float))
            and pd.notna(x) else None
        )
        return df


class VerificationExtractor(BaseExtractor):
    """Import journal entries from verlista.xlsx (85K+ rows)."""

    model_class = Verification
    mapping_key = 'verlista'
    batch_size = 10000  # Larger batches for this big file

    def clean_dataframe(self, df):
        df = super().clean_dataframe(df)

        # Convert date column
        df['date'] = pd.to_datetime(df['date'], errors='coerce').dt.date

        # Ensure account is integer
        df['account'] = pd.to_numeric(
            df['account'], errors='coerce'
        ).astype('Int64')

        # Convert debit/credit: None -> 0
        df['debit'] = pd.to_numeric(df['debit'], errors='coerce').fillna(0)
        df['credit'] = pd.to_numeric(df['credit'], errors='coerce').fillna(0)

        # Convert boolean
        df['preliminary'] = df['preliminary'].apply(
            lambda x: bool(x) if x is not None else False
        )

        # Ensure string fields
        for col in ['verification_number', 'text', 'cost_center',
                     'profit_center', 'project', 'specification',
                     'correction_ref', 'corrected_by', 'account_description']:
            if col in df.columns:
                df[col] = df[col].apply(
                    lambda x: str(x) if x is not None else None
                )

        # account as plain int (not Int64 for SQLite compatibility)
        df['account'] = df['account'].apply(
            lambda x: int(x) if x is not None and pd.notna(x) else None
        )

        return df
