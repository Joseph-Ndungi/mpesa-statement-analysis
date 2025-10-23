from flask import render_template, request, redirect, url_for, flash, Blueprint
import plotly
from forms import *
import glob
import os
import matplotlib.pyplot as plt
import pandas as pd
import re
import plotly.express as px
from datetime import date, datetime

insightsBp = Blueprint('insightsBp', __name__)

folderPath = 'uploads/'

csvFiles = glob.glob(os.path.join(folderPath, '*.csv'))


@insightsBp.route('/insights', methods=['GET', 'POST'])
def insights():
    form = DateForm()

    # --- Default configuration ---
    default_start = date(2025, 7, 15)
    default_end = date(2025, 7, 27)

    # --- Load uploaded CSVs safely ---
    uploads_dir = os.path.join(os.getcwd(), "uploads")
    try:
        csv_files = [
            os.path.join(uploads_dir, f)
            for f in os.listdir(uploads_dir)
            if f.endswith(".csv")
        ]
    except FileNotFoundError:
        flash("⚠️ Uploads directory not found.", "danger")
        return render_template('insights.html', title='Insights', form=form)

    if not csv_files:
        flash("⚠️ No transaction CSVs found in uploads directory.", "warning")
        return render_template('insights.html', title='Insights', form=form)

    # --- Read and combine CSVs with error handling ---
    df_list = []
    for file in csv_files:
        try:
            temp_df = pd.read_csv(file, parse_dates=['CompletionTime'])
            df_list.append(temp_df)
        except Exception as e:
            flash(f"⚠️ Error reading {os.path.basename(file)}: {e}", "danger")
            continue

    if not df_list:
        flash("⚠️ No valid CSV files could be read.", "danger")
        return render_template('insights.html', title='Insights', form=form)

    # --- Combine and clean data ---
    df = pd.concat(df_list, ignore_index=True)
    df["Withdrawn"] = pd.to_numeric(df["Withdrawn"], errors="coerce").abs()
    df["PaidIn"] = pd.to_numeric(df["PaidIn"], errors="coerce").fillna(0)

    # --- Determine date range ---
    if request.method == 'POST' and form.validate_on_submit():
        start_date = form.startDate.data or default_start
        end_date = form.endDate.data or default_end
    else:
        start_date = default_start
        end_date = default_end
        form.startDate.data = default_start
        form.endDate.data = default_end

    # --- Filter by selected range ---
    filtered_df = df[
        (df["CompletionTime"].dt.date >= start_date)
        & (df["CompletionTime"].dt.date <= end_date)
    ]

    # --- Handle empty dataset ---
    if filtered_df.empty:
        flash("⚠️ No transactions found for the selected date range.", "warning")
        return render_template(
            'insights.html',
            title='Insights',
            form=form,
            category_summary=[],
            top_counterparties_count=[],
            top_counterparties_value=[],
            category_graph=None,
            top_counterparties_graph=None
        )

    # --- Categorize Transactions ---
    def categorize_transaction(details: str) -> str:
        details = str(details).lower()
        if "merchant payment" in details or "buy goods" in details:
            return "Merchant Payment"
        elif "customer send money" in details or "transfer to" in details:
            return "Send Money"
        elif "receive money" in details or "transfer from" in details:
            return "Received Money"
        elif "withdraw" in details:
            return "Withdrawal"
        elif "mali" in details or "business payment from 859551" in details or "pay bill online to 859528" in details:
            return "Mali MMF"
        elif "paybill" in details or "pay bill" in details:
            return "Paybill Payment"
        elif "bank" in details:
            return "Bank Transaction"
        elif "od loan repayment" in details or "overdraft of credit party" in details:
            return "Fuliza / Loan"
        elif "airtime" in details or "bundle" in details:
            return "Airtime / Data"
        elif "reversal" in details:
            return "Reversal"
        elif "charge" in details or "fee" in details:
            return "Charges / Fees"
        else:
            return "Other"

    filtered_df["Category"] = filtered_df["Details"].apply(categorize_transaction)

    # --- Category Summary ---
    category_summary = (
        filtered_df.groupby("Category")[["PaidIn", "Withdrawn"]]
        .sum()
        .reset_index()
        .sort_values("Withdrawn", ascending=False)
    )
    category_summary["NetAmount"] = category_summary["PaidIn"] - category_summary["Withdrawn"]

    category_fig = px.bar(
        category_summary,
        x="Category",
        y=["PaidIn", "Withdrawn"],
        barmode="group",
        title="🏦 Inflow vs Outflow by Category",
        labels={"Category": "Transaction Category", "value": "Amount (KES)"},
        height=500,
    )
    category_graph = json.dumps(category_fig, cls=plotly.utils.PlotlyJSONEncoder)

    # --- Extract Counterparty ---
    def extract_counterparty(details: str) -> str:
        text = str(details).strip()
        match = re.search(r"(?:to|from)\s+(?:[-\w\s*]+)", text, re.I)
        if match:
            name = match.group(0)
            name = re.sub(r"^(to|from)\s+", "", name, flags=re.I)
            name = re.sub(r"[-:]+", "", name).strip()
            return name
        match = re.search(r"-\s*([A-Za-z\s]+)", text)
        if match:
            return match.group(1).strip()
        return "Unknown"

    filtered_df["Counterparty"] = filtered_df["Details"].apply(extract_counterparty)
    filtered_df["NetAmount"] = filtered_df["PaidIn"].fillna(0) - filtered_df["Withdrawn"].fillna(0)

    # --- Top 10 Counterparties ---
    top_counterparties_count = (
        filtered_df["Counterparty"].value_counts().head(10).reset_index()
    )
    top_counterparties_count.columns = ["Counterparty", "Count"]

    top_counterparties_value = (
        filtered_df.groupby("Counterparty")["NetAmount"]
        .sum()
        .abs()
        .sort_values(ascending=False)
        .head(10)
        .reset_index()
    )

    top_counterparties_fig = px.bar(
        top_counterparties_value,
        x="NetAmount",
        y="Counterparty",
        barmode='group',
        color='NetAmount',
        title="Top 10 Counterparties by Transaction Value",
    )
    top_counterparties_graph = json.dumps(top_counterparties_fig, cls=plotly.utils.PlotlyJSONEncoder)

    # --- Render Template ---
    return render_template(
        'insights.html',
        title='Insights',
        form=form,
        category_summary=category_summary.to_dict(orient='records'),
        top_counterparties_count=top_counterparties_count.to_dict(orient='records'),
        top_counterparties_value=top_counterparties_value.to_dict(orient='records'),
        category_graph=category_graph,
        top_counterparties_graph=top_counterparties_graph,
    )
