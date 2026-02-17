"""Extractors for order data: customer orders, purchase orders, quotes, intake."""

import pandas as pd
from app.extractors.base import BaseExtractor
from app.models.orders import CustomerOrder, PurchaseOrder, Quote, OrderIntake


class CustomerOrderExtractor(BaseExtractor):
    """Import customer orders from kundorderforteckning.xlsx."""

    model_class = CustomerOrder
    mapping_key = 'kundorderforteckning'

    def clean_dataframe(self, df):
        df = super().clean_dataframe(df)

        df['order_date'] = pd.to_datetime(df['order_date'], errors='coerce').dt.date

        for col in ['remaining_amount', 'remaining_amount_currency',
                     'exchange_rate', 'unit_price', 'unit_price_currency']:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        df['order_number'] = pd.to_numeric(
            df['order_number'], errors='coerce'
        ).apply(lambda x: int(x) if pd.notna(x) else None)

        df['customer_number'] = pd.to_numeric(
            df['customer_number'], errors='coerce'
        ).apply(lambda x: int(x) if pd.notna(x) else None)

        df['payment_terms'] = pd.to_numeric(
            df['payment_terms'], errors='coerce'
        ).apply(lambda x: int(x) if pd.notna(x) else None)

        # String fields
        df['customer_order_number'] = df['customer_order_number'].apply(
            lambda x: str(x) if x is not None else None
        )

        return df


class PurchaseOrderExtractor(BaseExtractor):
    """Import purchase orders from inkoporderforteckning.xlsx."""

    model_class = PurchaseOrder
    mapping_key = 'inkoporderforteckning'

    def clean_dataframe(self, df):
        df = super().clean_dataframe(df)

        # Date fields — convert then replace NaT with None
        for col in ['delivery_date', 'order_date', 'requested_delivery_date']:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce')
                df[col] = df[col].apply(
                    lambda x: x.date() if pd.notna(x) else None
                )

        # Numeric fields
        for col in ['unit_price', 'unit_price_currency', 'quantity_ordered',
                     'quantity_received', 'quantity_remaining',
                     'remaining_amount', 'amount_currency']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        # Integer fields — must handle NaN→None before int conversion
        for col in ['manufacturing_order', 'order_number', 'position', 'account']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                df[col] = df[col].apply(
                    lambda x: int(x) if x is not None and not (isinstance(x, float) and pd.isna(x)) else None
                )

        # Boolean fields
        for col in ['confirmed', 'is_purchase_order']:
            if col in df.columns:
                df[col] = df[col].apply(
                    lambda x: bool(x) if x is not None else False
                )

        # String coercion for customer_order and goods_marking (can be int/float in Excel)
        for col in ['goods_marking', 'customer_order', 'supplier_order_number',
                     'manufacturing_order_ref']:
            if col in df.columns:
                df[col] = df[col].apply(
                    lambda x: str(int(x)) if isinstance(x, (int, float)) and x is not None
                    and not (isinstance(x, float) and pd.isna(x))
                    else (str(x) if x is not None else None)
                )

        return df


class QuoteExtractor(BaseExtractor):
    """Import quotes from Offertförteckning-*.xlsx."""

    model_class = Quote
    mapping_key = 'offertforteckning'

    def clean_dataframe(self, df):
        df = super().clean_dataframe(df)

        for col in ['validity_date', 'delivery_date']:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce')
                df[col] = df[col].apply(
                    lambda x: x.date() if pd.notna(x) else None
                )

        for col in ['quantity', 'unit_price', 'discount', 'setup_price', 'amount']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        for col in ['customer_number', 'position']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                df[col] = df[col].apply(
                    lambda x: int(x) if x is not None and not (isinstance(x, float) and pd.isna(x)) else None
                )

        # inquiry_number can be large int from Excel
        if 'inquiry_number' in df.columns:
            df['inquiry_number'] = df['inquiry_number'].apply(
                lambda x: str(int(x)) if isinstance(x, (int, float)) and x is not None
                and not (isinstance(x, float) and pd.isna(x))
                else (str(x) if x is not None else None)
            )

        return df


class OrderIntakeExtractor(BaseExtractor):
    """Import order intake from Orderingång-*.xlsx."""

    model_class = OrderIntake
    mapping_key = 'orderingang'

    def clean_dataframe(self, df):
        df = super().clean_dataframe(df)

        # log_date is a datetime (with time component)
        df['log_date'] = pd.to_datetime(df['log_date'], errors='coerce')

        for col in ['quantity', 'price', 'value']:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        for col in ['order_number', 'customer_number', 'position']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').apply(
                    lambda x: int(x) if pd.notna(x) else None
                )

        return df
