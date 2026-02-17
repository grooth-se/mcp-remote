"""Extractors for inventory data: articles and minimum stock."""

import pandas as pd
from app.extractors.base import BaseExtractor
from app.models.inventory import Article, MinimumStock


class ArticleExtractor(BaseExtractor):
    """Import articles from Artikellista-*.xlsx."""

    model_class = Article
    mapping_key = 'artikellista'

    def clean_dataframe(self, df):
        df = super().clean_dataframe(df)

        for col in ['wip_balance', 'cleared_balance',
                     'available_balance', 'total_balance']:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        # article_number must be unique — drop duplicates keeping first
        df = df.drop_duplicates(subset=['article_number'], keep='first')

        return df


class MinimumStockExtractor(BaseExtractor):
    """Import minimum stock from Min stock per artikel.xlsx."""

    model_class = MinimumStock
    mapping_key = 'min_stock'

    def clean_dataframe(self, df):
        df = super().clean_dataframe(df)

        df['outer_diameter'] = pd.to_numeric(
            df['outer_diameter'], errors='coerce'
        )
        df['ordered_quantity'] = pd.to_numeric(
            df['ordered_quantity'], errors='coerce'
        ).fillna(0)

        return df
