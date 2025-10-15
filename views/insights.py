from flask import render_template, request, redirect, url_for, flash, Blueprint
import plotly
from forms import *
import glob
import os
import matplotlib.pyplot as plt
import pandas as pd
import re
import plotly.express as px

insightsBp = Blueprint('insightsBp', __name__)

folderPath = 'uploads/'

csvFiles = glob.glob(os.path.join(folderPath, '*.csv'))


# Read and combine all CSVs into one DataFrame
dfList = []
for file in csvFiles:
    tempDf = pd.read_csv(file, parse_dates=['CompletionTime'])
    dfList.append(tempDf)

# Concatenate all data into a single DataFrame
df = pd.concat(dfList, ignore_index=True)
# Drop duplicate transactions based on unique ReceiptNo
df = df.drop_duplicates(subset=["ReceiptNo"], keep="first").reset_index(drop=True)
df["Withdrawn"] = df["Withdrawn"].abs()


@insightsBp.route('/insights', methods=['GET', 'POST'])
def insights():
    form = DateForm()

    # --- Copy original data ---
    filtered_df = df.copy()

    # --- Apply date filters if provided ---
    if request.method == 'POST' and form.validate_on_submit():
        start_date = form.startDate.data
        end_date = form.endDate.data

        if start_date and end_date:
            mask = (filtered_df["CompletionTime"].dt.date >= start_date) & (
                filtered_df["CompletionTime"].dt.date <= end_date
            )
            filtered_df = filtered_df.loc[mask]
        elif start_date:
            filtered_df = filtered_df.loc[filtered_df["CompletionTime"].dt.date >= start_date]
        elif end_date:
            filtered_df = filtered_df.loc[filtered_df["CompletionTime"].dt.date <= end_date]

    # --- Handle case where no data remains ---
    if filtered_df.empty:
        flash("No transactions found for the selected date range.", "warning")
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

    categoryFig = px.bar(
        category_summary,
        x="Category",
        y=["PaidIn", "Withdrawn"],
        barmode="group",
        title="🏦 Inflow vs Outflow by Category",
        labels={"Category": "Transaction Category", "value": "Amount (KES)"},
        height=500,
    )
    categoryGraph = json.dumps(categoryFig, cls=plotly.utils.PlotlyJSONEncoder)

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

    topCounterpartiesFig = px.bar(
        top_counterparties_value,
        x="NetAmount",
        y="Counterparty",
        barmode='group',
        color='NetAmount',
        title="Top 10 Counterparties by Transaction Value",
    )
    topCounterpartiesGraph = json.dumps(topCounterpartiesFig, cls=plotly.utils.PlotlyJSONEncoder)

    # --- Render Template ---
    return render_template(
        'insights.html',
        title='Insights',
        form=form,
        category_summary=category_summary.to_dict(orient='records'),
        top_counterparties_count=top_counterparties_count.to_dict(orient='records'),
        top_counterparties_value=top_counterparties_value.to_dict(orient='records'),
        category_graph=categoryGraph,
        top_counterparties_graph=topCounterpartiesGraph,
    )
