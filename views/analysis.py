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

analysisBp = Blueprint('analysisBp', __name__)

UPLOAD_FOLDER = 'uploads/'


# --- Utility Functions --- #
def load_csv_data(folder_path: str) -> pd.DataFrame:
    """Read and combine all CSVs from the uploads folder."""
    csv_files = glob.glob(os.path.join(folder_path, '*.csv'))
    if not csv_files:
        raise FileNotFoundError("No CSV files found in the uploads folder.")

    df_list = []
    for file in csv_files:
        try:
            temp_df = pd.read_csv(file, parse_dates=['CompletionTime'])
            df_list.append(temp_df)
        except Exception as e:
            print(f"⚠️ Skipping {file}: {e}")

    if not df_list:
        raise ValueError("No valid CSV data could be read.")
    
    df = pd.concat(df_list, ignore_index=True)
    df["Withdrawn"] = df["Withdrawn"].abs()
    return df


def categorize_transaction(details: str) -> str:
    details = str(details).lower()
    if "merchant payment" in details or "buy goods" in details:
        return "Merchant Payment"
    elif "customer send money" in details or "transfer to" in details:
        return "Person-to-Person"
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
    return "Other"


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


@analysisBp.route('/analysis', methods=['GET', 'POST'])
def analysis():
    form = FilterForm()

    # --- Default configuration --- #
    default_start = date(2025, 7, 15)
    default_end = date(2025, 7, 27)
    default_period = "M"  # Monthly by default

    # --- Load Data Safely --- #
    try:
        df = load_csv_data(UPLOAD_FOLDER)
    except Exception as e:
        flash(str(e), "danger")
        return render_template('analysis.html', title='Analysis', form=form)

    # --- Categorize and Extract Counterparties --- #
    df["Category"] = df["Details"].apply(categorize_transaction)
    df["Counterparty"] = df["Details"].apply(extract_counterparty)

    # --- Handle Filters (with defaults) --- #
    if request.method == "POST" and form.validate_on_submit():
        start_date = form.startDate.data or default_start
        end_date = form.endDate.data or default_end
        selected_period = form.period.data or default_period
    else:
        start_date = default_start
        end_date = default_end
        selected_period = default_period
        form.startDate.data = default_start
        form.endDate.data = default_end
        form.period.data = default_period

    # --- Apply Date Filtering --- #
    filtered_df = df[
        (df["CompletionTime"].dt.date >= start_date)
        & (df["CompletionTime"].dt.date <= end_date)
    ]

    if filtered_df.empty:
        flash("⚠️ No transactions found in the selected date range.", "warning")
        return render_template(
            "analysis.html",
            title="Analysis",
            form=form,
            cashflow=None,
            cashflow_graph=None,
            category_graph=None,
            merchant_graph=None
        )

    # --- Cashflow Analysis --- #
    period_label = "Month" if selected_period == "M" else "Week"
    filtered_df[period_label] = filtered_df["CompletionTime"].dt.to_period(selected_period)

    cashflow = filtered_df.groupby(period_label).agg(
        Inflow=("PaidIn", "sum"),
        Outflow=("Withdrawn", "sum")
    ).reset_index()

    cashflow["NetFlow"] = cashflow["Inflow"] - cashflow["Outflow"]
    cashflow[period_label] = cashflow[period_label].astype(str)

    # --- Plot Cashflow --- #
    cashflow_melted = cashflow.melt(
        id_vars=period_label,
        value_vars=["Inflow", "Outflow", "NetFlow"],
        var_name="FlowType",
        value_name="Amount"
    )

    cashflow_fig = px.line(
        cashflow_melted,
        x=period_label,
        y="Amount",
        color="FlowType",
        markers=True,
        title=f"📆 {period_label}ly M-PESA Cash Flow",
        line_dash="FlowType",
        color_discrete_map={"Inflow": "green", "Outflow": "red", "NetFlow": "blue"},
    )
    cashflow_fig.update_layout(
        xaxis_title=period_label,
        yaxis_title="Amount (KES)",
        legend_title="Flow Type",
        template="plotly_white",
        title_x=0.5,
        margin=dict(l=40, r=40, t=60, b=40)
    )
    cashflow_graph = json.dumps(cashflow_fig, cls=plotly.utils.PlotlyJSONEncoder)

    # --- Category Trends --- #
    def category_trends_over_time(df, period="M"):
        df["Period"] = df["CompletionTime"].dt.to_period(period).astype(str)
        category_trends = (
            df.groupby(["Period", "Category"])
            .agg(Total_Spent=("Withdrawn", "sum"))
            .reset_index()
        )

        top_categories = (
            df.groupby("Category")["Withdrawn"]
            .sum()
            .sort_values(ascending=False)
            .head(5)
            .index
        )

        plot_data = category_trends[category_trends["Category"].isin(top_categories)]
        label = "Monthly" if period == "M" else "Weekly"

        fig = px.line(
            plot_data,
            x="Period",
            y="Total_Spent",
            color="Category",
            markers=True,
            title=f"📊 {label} Spending Trends by Category",
            labels={"Total_Spent": "Total Spent (KES)", "Period": label}
        )
        fig.update_layout(template="plotly_white", legend_title_text="Category", xaxis_tickangle=-45)
        return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

    # --- Merchant Trends --- #
    def merchant_trends_over_time(df, period="M"):
        df["Period"] = df["CompletionTime"].dt.to_period(period).astype(str)
        merchant_trends = (
            df.groupby(["Period", "Counterparty"])
            .agg(Total_Spent=("Withdrawn", "sum"))
            .reset_index()
        )

        top_merchants = (
            df.groupby("Counterparty")["Withdrawn"]
            .sum()
            .sort_values(ascending=False)
            .head(5)
            .index
        )

        plot_data = merchant_trends[merchant_trends["Counterparty"].isin(top_merchants)]
        label = "Monthly" if period == "M" else "Weekly"

        fig = px.line(
            plot_data,
            x="Period",
            y="Total_Spent",
            color="Counterparty",
            markers=True,
            title=f"🏪 {label} Spending by Top Merchants",
            labels={"Total_Spent": "Total Spent (KES)", "Period": label}
        )
        fig.update_layout(template="plotly_white", legend_title_text="Merchant", xaxis_tickangle=-45)
        return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

    # --- Generate Graphs --- #
    category_graph = category_trends_over_time(filtered_df, period=selected_period)
    merchant_graph = merchant_trends_over_time(filtered_df, period=selected_period)

    # --- Render Template --- #
    return render_template(
        "analysis.html",
        title="Analysis",
        form=form,
        selected_period=selected_period,
        cashflow=cashflow.to_dict("records"),
        cashflow_graph=cashflow_graph,
        category_graph=category_graph,
        merchant_graph=merchant_graph
    )

