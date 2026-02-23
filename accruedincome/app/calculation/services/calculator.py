"""Accrued Income Calculator - Core calculation logic.

Ported from legacy acrued5.py calculation_core() method.
Implements K3/IFRS 15 percentage of completion calculations.
"""

import os
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flask import current_app


class AccruedIncomeCalculator:
    """Calculate accrued income per project using percentage of completion method."""

    # Constants
    COMPLETION_THRESHOLD = 0.99  # cc
    HOUR_COST = 475  # SEK per hour

    # Column name mapping: Swedish -> normalized
    COLUMN_MAPPING = {
        'Förvän. intäkt': 'Forvan. intakt',
        'Förvän. kostnad': 'Forvan. kostnad',
        'Utf., intäkt': 'Utf., intakt',
        'Utf., kostnad': 'Utf., kostnad',
        'Rest. intäkt': 'Rest. intakt',
        'Benämning': 'Benamning',
        'Artikel – Artikelnummer': 'Artikel - Artikelnummer',  # en-dash to hyphen
        'À-pris': 'A-pris',
        'À-pris val.': 'A-pris val.',
    }

    def __init__(self, file_paths: dict, output_folder: str):
        """Initialize calculator with file paths.

        Args:
            file_paths: Dict mapping file keys to file paths
            output_folder: Directory for output files
        """
        self.file_paths = file_paths
        self.output_folder = output_folder
        self.dataframes = {}
        self.result_df = None
        self.closing_date = None
        self._gl_summary = None  # Pre-aggregated GL data (from integration)

    def normalize_columns(self, df):
        """Normalize Swedish column names to ASCII equivalents."""
        rename_map = {}
        for col in df.columns:
            new_col = col
            for swedish, normalized in self.COLUMN_MAPPING.items():
                if col == swedish:
                    new_col = normalized
                    break
            rename_map[col] = new_col
        return df.rename(columns=rename_map)

    def load_files(self):
        """Load all Excel files into DataFrames."""
        # Load with openpyxl engine to avoid xlrd issues
        engine = 'openpyxl'

        self.dataframes['valutakurser'] = pd.read_excel(
            self.file_paths['valutakurser'], engine=engine)
        self.dataframes['projectadjustments'] = pd.read_excel(
            self.file_paths['projectadjustments'], engine=engine)
        self.dataframes['CO_proj_crossref'] = pd.read_excel(
            self.file_paths['CO_proj_crossref'], engine=engine)
        self.dataframes['projektuppf'] = self.normalize_columns(pd.read_excel(
            self.file_paths['projektuppf'], engine=engine))
        self.dataframes['inkoporderforteckning'] = self.normalize_columns(pd.read_excel(
            self.file_paths['inkoporderforteckning'], engine=engine))
        self.dataframes['kundorderforteckning'] = pd.read_excel(
            self.file_paths['kundorderforteckning'], engine=engine)
        self.dataframes['kontoplan'] = pd.read_excel(
            self.file_paths['kontoplan'], engine=engine)
        self.dataframes['verlista'] = pd.read_excel(
            self.file_paths['verlista'], engine=engine)
        self.dataframes['tiduppfoljning'] = pd.read_excel(
            self.file_paths['tiduppfoljning'], engine=engine)
        self.dataframes['faktureringslogg'] = self.normalize_columns(pd.read_excel(
            self.file_paths['faktureringslogg'], engine=engine))
        self.dataframes['Accuredhistory'] = self.normalize_columns(pd.read_excel(
            self.file_paths['Accuredhistory'], engine=engine))

        # Remove first column from history (usually index)
        self.dataframes['Accuredhistory'] = \
            self.dataframes['Accuredhistory'].iloc[:, 1:]

    def load_from_dataframes(self, dataframes: dict):
        """Load pre-built DataFrames instead of reading Excel files.

        Used by the integration loader to inject API-sourced data.

        Args:
            dataframes: Dict mapping file keys to pandas DataFrames.
                        May include a 'gl_summary' key with pre-aggregated
                        GL data (income_by_project, cost_by_project dicts).
        """
        # Extract gl_summary before storing DataFrames
        if 'gl_summary' in dataframes:
            self._gl_summary = dataframes.pop('gl_summary')

        self.dataframes = dataframes

    def revaluate_purchase_orders(self):
        """Revaluate purchase orders at closing exchange rates."""
        dfval = self.dataframes['valutakurser']
        dfinkop = self.dataframes['inkoporderforteckning']
        dfprojuppf = self.dataframes['projektuppf']

        if dfinkop.empty or dfval.empty:
            dfprojuppf['Remaining cost'] = 0
            self.dataframes['projektuppf'] = dfprojuppf
            return

        # Get latest exchange rates
        dfinkop['act cur'] = float(dfval['SEK'].iloc[-1])
        dfinkop.loc[dfinkop['Valuta'] == 'DKK', 'act cur'] = \
            float(dfval['DKK'].iloc[-1])
        dfinkop.loc[dfinkop['Valuta'] == 'EUR', 'act cur'] = \
            float(dfval['EUR'].iloc[-1])
        dfinkop.loc[dfinkop['Valuta'] == 'GBP', 'act cur'] = \
            float(dfval['GBP'].iloc[-1])
        dfinkop.loc[dfinkop['Valuta'] == 'NOK', 'act cur'] = \
            float(dfval['NOK'].iloc[-1])
        dfinkop.loc[dfinkop['Valuta'] == 'USD', 'act cur'] = \
            float(dfval['USD'].iloc[-1])

        # Extract project references from descriptions
        dfinkop['projref'] = dfinkop['Benamning'].str.slice(0, 8) \
            if 'Benamning' in dfinkop.columns else ''
        dfinkop['projref1'] = dfinkop['Artikelnummer'].str.slice(0, 8) \
            if 'Artikelnummer' in dfinkop.columns else ''

        # Calculate currency-adjusted amount
        dfinkop['curadj'] = dfinkop['Belopp val.'] * dfinkop['act cur']

        # Sum remaining cost by project
        dfprojuppf['Remaining cost'] = dfprojuppf['Projektnummer'].map(
            dfinkop.groupby('Projekt')['curadj'].sum()
        )

        self.dataframes['inkoporderforteckning'] = dfinkop
        self.dataframes['projektuppf'] = dfprojuppf

    def apply_project_adjustments(self):
        """Apply adjustments from projectadjustments.xlsx."""
        dfprojadj = self.dataframes['projectadjustments'].copy()
        dfprojuppf = self.dataframes['projektuppf'].copy()

        if dfprojuppf.empty:
            for col in ['incl', 'complex', 'incomeadj', 'costcalcadj',
                        'puradj', 'closing']:
                dfprojuppf[col] = None
            self.dataframes['projektuppf'] = dfprojuppf
            self.dataframes['projectadjustments'] = dfprojadj
            return

        # Set index on project number
        dfprojuppf.set_index('Projektnummer', inplace=True)
        dfprojadj.set_index('Projektnummer', inplace=True)

        # Drop columns we'll recalculate
        cols_to_drop = ['Startdatum', 'Slutdatum', 'Rest. kostnad', 'Rest. intakt']
        dfprojuppf.drop(
            [c for c in cols_to_drop if c in dfprojuppf.columns],
            axis=1, inplace=True
        )

        # Map adjustment fields
        dfprojuppf['incl'] = dfprojadj['Accured']
        dfprojuppf['complex'] = dfprojadj['Contingency']
        dfprojuppf['incomeadj'] = dfprojadj['Incomeadj']
        dfprojuppf['costcalcadj'] = dfprojadj['Costcalcadj']
        dfprojuppf['puradj'] = dfprojadj['puradj']
        dfprojuppf['closing'] = dfprojadj['Closing']

        self.dataframes['projektuppf'] = dfprojuppf
        self.dataframes['projectadjustments'] = dfprojadj

    def calculate_basic_metrics(self):
        """Calculate basic POC metrics: vinstmarg, kostfakt, fardiggrad."""
        df = self.dataframes['projektuppf']

        # Profit margin: (Expected Income - Expected Cost) / Expected Income
        df['vinstmarg'] = np.where(
            df['Forvan. intakt'] != 0,
            (df['Forvan. intakt'] - df['Forvan. kostnad']) / df['Forvan. intakt'],
            0
        )

        # Cost factor for invoiced work
        df['kostfakt'] = df['Utf., intakt'] * (1 - df['vinstmarg'])

        # Completion rate (fardiggrad)
        denominator = df['Forvan. kostnad'] - df['kostfakt']
        numerator = df['Utf., kostnad'] - df['kostfakt']
        df['fardiggrad'] = np.where(
            denominator != 0,
            numerator / denominator,
            0
        )

        # Basic accrued income
        df['accured income'] = df['fardiggrad'] * \
            (df['Forvan. intakt'] - df['Utf., intakt'])

        # Clean up infinities and NaN
        numeric_cols = df.select_dtypes(include='number').columns
        df[numeric_cols] = df[numeric_cols].replace([np.inf, -np.inf], 0)
        df[numeric_cols] = df[numeric_cols].fillna(0)

        # Risk/contingency
        df['risk'] = df['accured income'] * df['complex']
        df.loc[df['fardiggrad'] > self.COMPLETION_THRESHOLD, 'risk'] = 0

        # Override for fully invoiced projects
        df.loc[df['Utf., intakt'] == df['Forvan. intakt'], 'fardiggrad'] = 1
        df.loc[df['fardiggrad'] == 1, 'accured income'] = 0
        df.loc[df['incl'] == False, 'accured income'] = 0

        numeric_cols = df.select_dtypes(include='number').columns
        df[numeric_cols] = df[numeric_cols].replace([np.inf, -np.inf], 0)
        df[numeric_cols] = df[numeric_cols].fillna(0)

        self.dataframes['projektuppf'] = df

    def extract_actual_from_gl(self):
        """Extract actual income and cost from verification list (GL).

        If pre-aggregated GL summary is available (from integration),
        use it directly instead of processing raw verification rows.
        """
        dfprojuppf = self.dataframes['projektuppf']

        if self._gl_summary:
            # Use pre-aggregated data from MG5integration API
            income_map = self._gl_summary.get('income_by_project', {})
            cost_map = self._gl_summary.get('cost_by_project', {})

            dfprojuppf['act income'] = dfprojuppf.index.map(
                lambda proj: income_map.get(str(proj), 0)
            )
            dfprojuppf['act cost'] = dfprojuppf.index.map(
                lambda proj: cost_map.get(str(proj), 0)
            )
        else:
            # Original path: process raw verlista Excel data
            dfverl = self.dataframes['verlista']

            # Income: accounts 3000-3999
            income_trans = dfverl[(dfverl['Konto'] >= 3000) & (dfverl['Konto'] <= 3999)]
            actinkre = income_trans.groupby('Proj.')['Kredit'].sum()
            actindeb = income_trans.groupby('Proj.')['Debet'].sum()
            actincome = actinkre - actindeb

            # Cost: accounts 4000-6999, excluding 4940 and 4950
            cost_trans = dfverl[
                (dfverl['Konto'] >= 4000) &
                (dfverl['Konto'] <= 6999) &
                (dfverl['Konto'] != 4940) &
                (dfverl['Konto'] != 4950)
            ]
            actcokre = cost_trans.groupby('Proj.')['Kredit'].sum()
            actcodeb = cost_trans.groupby('Proj.')['Debet'].sum()
            actcost = actcodeb - actcokre

            dfprojuppf['act income'] = actincome
            dfprojuppf['act cost'] = actcost

        self.dataframes['projektuppf'] = dfprojuppf

    def process_time_reports(self):
        """Process time tracking data."""
        dftid = self.dataframes['tiduppfoljning']
        dfprojuppf = self.dataframes['projektuppf']

        if dftid.empty:
            dfprojuppf['CM cost'] = 0
            self.dataframes['projektuppf'] = dfprojuppf
            return

        # Calculate cost from hours
        dftid['CM cost'] = dftid['Utfall'] * self.HOUR_COST
        dfprojuppf['CM cost'] = dftid.groupby('Projektnummer')['CM cost'].sum()

        self.dataframes['tiduppfoljning'] = dftid
        self.dataframes['projektuppf'] = dfprojuppf

    def revaluate_customer_orders(self):
        """Revaluate customer orders at closing exchange rates."""
        dfval = self.dataframes['valutakurser']
        dfkund = self.dataframes['kundorderforteckning']
        dfcoref = self.dataframes['CO_proj_crossref']
        dfprojuppf = self.dataframes['projektuppf']

        if dfkund.empty or dfval.empty:
            dfprojuppf['Remaining income'] = 0
            dfprojuppf['Remaining income val.'] = 0
            self.dataframes['projektuppf'] = dfprojuppf
            return

        # Standardize column name
        dfkund.rename(columns={'Ordernummer': 'ordernummer'}, inplace=True)

        # Apply exchange rates
        dfkund['act cur'] = float(dfval['SEK'].iloc[-1])
        dfkund.loc[dfkund['Valuta'] == 'DKK', 'act cur'] = \
            float(dfval['DKK'].iloc[-1])
        dfkund.loc[dfkund['Valuta'] == 'EUR', 'act cur'] = \
            float(dfval['EUR'].iloc[-1])
        dfkund.loc[dfkund['Valuta'] == 'GBP', 'act cur'] = \
            float(dfval['GBP'].iloc[-1])
        dfkund.loc[dfkund['Valuta'] == 'NOK', 'act cur'] = \
            float(dfval['NOK'].iloc[-1])
        dfkund.loc[dfkund['Valuta'] == 'USD', 'act cur'] = \
            float(dfval['USD'].iloc[-1])

        # Map orders to projects via cross-reference
        for index, row in dfkund.iterrows():
            order_num = dfkund['ordernummer'].values[index]
            matches = dfcoref.index[dfcoref['Ordernummer'] == order_num].tolist()
            if matches:
                project = dfcoref['Projekt'].values[matches[0]]
                dfkund.at[index, 'Projekt'] = project

        # Calculate currency-adjusted amounts
        dfkund['curadj'] = dfkund['Restbelopp val.'] * dfkund['act cur']
        dfprojuppf['Remaining income'] = dfkund.groupby('Projekt')['curadj'].sum()
        dfprojuppf['Remaining income val.'] = \
            dfkund.groupby('Projekt')['Restbelopp val.'].sum()

        self.dataframes['kundorderforteckning'] = dfkund
        self.dataframes['projektuppf'] = dfprojuppf

    def process_milestones(self):
        """Process milestone/billing data."""
        dfmile = self.dataframes['faktureringslogg']
        dfkund = self.dataframes['kundorderforteckning']
        dfprojuppf = self.dataframes['projektuppf']

        if dfmile.empty:
            dfprojuppf['Milestone'] = 0
            dfprojuppf['Milestone CUR'] = 0
            self.dataframes['projektuppf'] = dfprojuppf
            return

        dfmile.rename(columns={'Ordernummer': 'ordernummer'}, inplace=True)

        # Mark milestone articles (F100, F110, F120, F130)
        milestone_articles = ['F100', 'F110', 'F120', 'F130']
        dfmile['sortkey'] = np.nan
        for article in milestone_articles:
            dfmile.loc[dfmile['Artikel - Artikelnummer'] == article, 'sortkey'] = 1

        # Map milestones to projects
        if not dfkund.empty and 'ordernummer' in dfkund.columns:
            for index, row in dfmile.iterrows():
                order_num = dfmile['ordernummer'].values[index]
                matches = dfkund.index[dfkund['ordernummer'] == order_num].tolist()
                if matches:
                    project = dfkund['Projekt'].values[matches[0]]
                    dfmile.at[index, 'Projekt'] = project

        # Filter to milestones only
        dfmile = dfmile[dfmile['sortkey'].notna()]

        # Aggregate by project
        if 'Projekt' in dfmile.columns:
            dfprojuppf['Milestone'] = dfmile.groupby('Projekt')['Belopp'].sum()
            dfprojuppf['Milestone CUR'] = dfmile.groupby('Projekt')['Belopp val.'].sum()
        else:
            dfprojuppf['Milestone'] = 0
            dfprojuppf['Milestone CUR'] = 0

        self.dataframes['faktureringslogg'] = dfmile
        self.dataframes['projektuppf'] = dfprojuppf

    def calculate_currency_adjusted_totals(self):
        """Calculate currency-adjusted totals and final accrued income."""
        df = self.dataframes['projektuppf']

        # Clean up
        numeric_cols = df.select_dtypes(include='number').columns
        df[numeric_cols] = df[numeric_cols].replace([np.inf, -np.inf], 0)
        df[numeric_cols] = df[numeric_cols].fillna(0)

        # Remaining income with milestone adjustment
        df['Remaining income CUR'] = df['Milestone'] + \
            np.where(
                df['Remaining income val.'] != 0,
                (df['Remaining income val.'] - df['Milestone CUR']) *
                (df['Remaining income'] / df['Remaining income val.']),
                0
            )
        df.loc[df['Remaining income CUR'] > 0, 'Remaining income'] = \
            df['Remaining income CUR']

        # Actual income/cost with adjustments
        df['actincome CUR'] = df['act income'] + df['incomeadj']
        df['totalincome CUR'] = df['actincome CUR'] + df['Remaining income']
        df['actcost CUR'] = df['act cost'] + df['puradj'] + df['CM cost']
        df['totalcost CUR'] = df['actcost CUR'] + df['Remaining cost'] + \
            df['costcalcadj']

        # Profit margin (currency adjusted)
        df['profit margin CUR'] = np.where(
            df['totalincome CUR'] != 0,
            (df['totalincome CUR'] - df['totalcost CUR']) / df['totalincome CUR'],
            0
        )

        # Cost for invoiced portion
        df['actcost invo CUR'] = df['actincome CUR'] * (1 - df['profit margin CUR'])

        # Completion metrics
        df['completion CUR'] = np.where(
            df['totalcost CUR'] != 0,
            df['actcost CUR'] / df['totalcost CUR'],
            0
        )

        denominator = df['totalcost CUR'] - df['actcost invo CUR']
        numerator = df['actcost CUR'] - df['actcost invo CUR']
        df['completion CUR1'] = np.where(
            denominator != 0,
            numerator / denominator,
            0
        )

        df.loc[df['Remaining income CUR'] == 0, 'completion CUR'] = 1

        # Final accrued income (currency adjusted)
        df['accured income CUR'] = df['completion CUR1'] * df['Remaining income']

        # Contingency (currency adjusted)
        df['contingency CUR'] = df['accured income CUR'] * df['complex']
        df.loc[df['contingency CUR'] < 0, 'contingency CUR'] = \
            -1 * df['contingency CUR']
        df.loc[df['completion CUR1'] > self.COMPLETION_THRESHOLD,
               'contingency CUR'] = 0
        df.loc[df['completion CUR1'] > self.COMPLETION_THRESHOLD,
               'accured income CUR'] = 0
        df.loc[df['incl'] == False, 'accured income CUR'] = 0

        numeric_cols = df.select_dtypes(include='number').columns
        df[numeric_cols] = df[numeric_cols].replace([np.inf, -np.inf], 0)
        df[numeric_cols] = df[numeric_cols].fillna(0)

        self.dataframes['projektuppf'] = df

    def calculate_variance(self):
        """Calculate variance metrics."""
        df = self.dataframes['projektuppf']

        df['projloss'] = df['totalincome CUR'] - df['totalcost CUR']
        df['diffincome'] = df['Forvan. intakt'] - df['Remaining income'] - \
            df['act income'] - df['incomeadj']
        df['diffcost'] = df['Forvan. kostnad'] - df['Remaining cost'] - \
            df['act cost'] - df['CM cost'] - df['costcalcadj'] + df['puradj']

        numeric_cols = df.select_dtypes(include='number').columns
        df[numeric_cols] = df[numeric_cols].replace([np.inf, -np.inf], 0)
        df[numeric_cols] = df[numeric_cols].fillna(0)

        self.dataframes['projektuppf'] = df

    def generate_charts(self):
        """Generate project progress charts."""
        df = self.dataframes['projektuppf'].copy()
        dfacchist = self.dataframes['Accuredhistory']

        if df.empty and (dfacchist is None or dfacchist.empty):
            return

        # Ensure closing is datetime
        df['closing'] = pd.to_datetime(df['closing'], errors='coerce')

        # Add project number as column (it's currently the index)
        if not df.empty:
            df = df.reset_index(names='Projektnummer')

        # Combine with history
        dfs = [d.dropna(axis=1, how='all') for d in [dfacchist, df]
               if d is not None and not d.empty]
        dfacchist = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

        # Create charts folder
        charts_folder = os.path.join(self.output_folder, 'charts')
        os.makedirs(charts_folder, exist_ok=True)

        # Group by project
        dfchartdata = dfacchist.groupby('Projektnummer')
        projects = dfacchist['Projektnummer'].unique()

        for proj in projects:
            try:
                proj_data = dfchartdata.get_group(proj)
                plt.figure(figsize=(10, 6))

                x = proj_data['closing']
                y1 = proj_data['actcost CUR']
                y2 = proj_data['actincome CUR'] + proj_data['accured income CUR']
                y3 = proj_data['totalcost CUR']
                y4 = proj_data['totalincome CUR']

                plt.plot(x, y1, color='black', label='Actual Cost', linestyle='-', linewidth=1.5)
                plt.plot(x, y2, color='darkred', label='Income + Accrued', linestyle='-', linewidth=1.5)
                plt.plot(x, y3, color='dimgray', label='Total Cost', linestyle='--', linewidth=1.5)
                plt.plot(x, y4, color='darkgreen', label='Total Income', linestyle='--', linewidth=1.5)

                plt.legend()
                plt.title(f'Project: {proj}')
                plt.xlabel('Closing Date')
                plt.ylabel('Amount (SEK)')
                plt.xticks(rotation=45)
                plt.tight_layout()

                plt.savefig(os.path.join(charts_folder, f'{proj}.png'))
                plt.close()
            except Exception:
                continue

        self.dataframes['Accuredhistory'] = dfacchist

    def run(self, dataframes=None, closing_date=None):
        """Execute complete calculation pipeline.

        Args:
            dataframes: Optional dict of pre-built DataFrames (from integration).
                        If provided, skips load_files() and uses these instead.
            closing_date: Optional closing date override (YYYY-MM-DD string).
                          If provided, uses this instead of extracting from
                          projectadjustments.

        Returns:
            tuple: (result_dataframe, closing_date)
        """
        # Load data from either pre-built DataFrames or Excel files
        if dataframes:
            self.load_from_dataframes(dataframes)
        else:
            self.load_files()

        # Early return if no project data to calculate
        if self.dataframes.get('projektuppf') is None or \
                self.dataframes['projektuppf'].empty:
            self.result_df = pd.DataFrame()
            self.closing_date = closing_date or \
                pd.Timestamp.now().strftime('%Y-%m-%d')
            return self.result_df, self.closing_date

        # Step 1: Revaluate purchase orders
        self.revaluate_purchase_orders()

        # Step 2: Apply project adjustments
        self.apply_project_adjustments()

        # Step 3: Calculate basic metrics
        self.calculate_basic_metrics()

        # Step 4: Extract actual income/cost from GL
        self.extract_actual_from_gl()

        # Step 5: Process time reports
        self.process_time_reports()

        # Step 6: Revaluate customer orders
        self.revaluate_customer_orders()

        # Step 7: Process milestones
        self.process_milestones()

        # Step 8: Calculate currency-adjusted totals
        self.calculate_currency_adjusted_totals()

        # Step 9: Calculate variance
        self.calculate_variance()

        # Step 10: Generate charts
        self.generate_charts()

        # Get result and closing date
        self.result_df = self.dataframes['projektuppf']

        # Extract closing date (use override if provided)
        if closing_date:
            self.closing_date = closing_date
        else:
            self.result_df['closing'] = pd.to_datetime(
                self.result_df['closing'], errors='coerce')
            closing_dates = self.result_df['closing'].dropna()
            if len(closing_dates) > 0:
                self.closing_date = closing_dates.iloc[0].strftime('%Y-%m-%d')
            else:
                self.closing_date = pd.Timestamp.now().strftime('%Y-%m-%d')

        # Export to Excel
        report_path = os.path.join(
            self.output_folder,
            f'{self.closing_date}_report.xlsx'
        )
        self.result_df.to_excel(report_path)

        # Export updated history
        history_path = os.path.join(
            self.output_folder,
            f'{self.closing_date}_accuredhistory.xlsx'
        )
        self.dataframes['Accuredhistory'].to_excel(history_path)

        return self.result_df, self.closing_date
