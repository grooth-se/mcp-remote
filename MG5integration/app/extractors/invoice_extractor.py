"""Extractors for invoicing data: invoice log and exchange rates."""

import pandas as pd
from app.extractors.base import BaseExtractor
from app.models.invoicing import InvoiceLog, ExchangeRate


class InvoiceLogExtractor(BaseExtractor):
    """Import invoice log from faktureringslogg.xlsx."""

    model_class = InvoiceLog
    mapping_key = 'faktureringslogg'

    def clean_dataframe(self, df):
        df = super().clean_dataframe(df)

        df['date'] = pd.to_datetime(df['date'], errors='coerce').dt.date

        for col in ['unit_price', 'unit_price_currency', 'amount',
                     'amount_currency', 'exchange_rate']:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        df['invoice_number'] = pd.to_numeric(
            df['invoice_number'], errors='coerce'
        ).apply(lambda x: int(x) if pd.notna(x) else None)

        df['order_number'] = pd.to_numeric(
            df['order_number'], errors='coerce'
        ).apply(lambda x: int(x) if pd.notna(x) else None)

        df['forward_rate'] = df['forward_rate'].apply(
            lambda x: bool(x) if x is not None else False
        )

        return df


class ExchangeRateExtractor(BaseExtractor):
    """Import exchange rates from valutakurser.xlsx."""

    model_class = ExchangeRate
    mapping_key = 'valutakurser'

    def clean_dataframe(self, df):
        df = super().clean_dataframe(df)

        df['date'] = pd.to_datetime(df['date'], errors='coerce').dt.date

        for col in ['dkk', 'eur', 'gbp', 'nok', 'sek', 'usd']:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        # Drop rows without date
        df = df.dropna(subset=['date'])

        return df
