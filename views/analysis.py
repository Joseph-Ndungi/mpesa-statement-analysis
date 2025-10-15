from flask import render_template, request, redirect, url_for, flash, Blueprint
import plotly
from forms import *
import glob
import os
import matplotlib.pyplot as plt
import pandas as pd
import re
import plotly.express as px

analysisBp = Blueprint('analysisBp', __name__)

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
#df = df.drop_duplicates(subset=["ReceiptNo"], keep="first").reset_index(drop=True)
df["Withdrawn"] = df["Withdrawn"].abs()

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
    elif "mali" in details or "Business Payment from 859551" in details or "Pay Bill Online to 859528" in details:
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

# --- Apply categorization ---
df["Category"] = df["Details"].apply(categorize_transaction)

def extract_counterparty(details: str) -> str:
    """
    Extract likely counterparty name or business from M-PESA transaction details.
    """
    text = str(details).strip()

    # Examples of patterns to catch:
    # "Pay Bill Online to 222111 - Family Bank"
    # "Customer Send Money to 07******478 SOFIA MASIKA"
    # "Business Payment from 859551 - MALI"
    match = re.search(r"(?:to|from)\s+(?:[-\w\s*]+)", text, re.I)
    if match:
        name = match.group(0)
        # Clean up
        name = re.sub(r"^(to|from)\s+", "", name, flags=re.I)
        name = re.sub(r"[-:]+", "", name).strip()
        return name

    # fallback: maybe the name follows a hyphen (e.g., "- MALI")
    match = re.search(r"-\s*([A-Za-z\s]+)", text)
    if match:
        return match.group(1).strip()

    return "Unknown"

df["Counterparty"] = df["Details"].apply(extract_counterparty)


@analysisBp.route('/analysis', methods=['GET', 'POST'])
def analysis():
    form = FilterForm()

    # --- Make a copy to avoid mutating global df ---
    filtered_df = df.copy()

    # --- Apply date filters if provided ---
    if request.method == 'POST' and form.validate_on_submit():
        start_date = form.startDate.data
        end_date = form.endDate.data
        selected_period = form.period.data or "M"  # M = Monthly, W = Weekly
    else:
        selected_period = "M"  # Default to Monthly

    # Filter data by date range if applicable
    if request.method == 'POST' and form.validate_on_submit():
        if start_date and end_date:
            mask = (filtered_df["CompletionTime"].dt.date >= start_date) & (
                filtered_df["CompletionTime"].dt.date <= end_date
            )
            filtered_df = filtered_df.loc[mask]
        elif start_date:
            filtered_df = filtered_df.loc[filtered_df["CompletionTime"].dt.date >= start_date]
        elif end_date:
            filtered_df = filtered_df.loc[filtered_df["CompletionTime"].dt.date <= end_date]

    if filtered_df.empty:
        flash("No transactions found for the selected filters.", "warning")
        return render_template(
            'analysis.html',
            title='Analysis',
            form=form,
            cashflow=None,
            cashflow_graph=None,
            category_monthly_graph=None,
            merchant_monthly_graph=None
        )

    # --- Cashflow Analysis ---
    period_label = "Month" if selected_period == "M" else "Week"
    filtered_df[period_label] = filtered_df["CompletionTime"].dt.to_period(selected_period)

    cashflow = filtered_df.groupby(period_label).agg(
        Inflow=("PaidIn", "sum"),
        Outflow=("Withdrawn", "sum")
    ).reset_index()

    cashflow["NetFlow"] = cashflow["Inflow"] - cashflow["Outflow"]
    cashflow[period_label] = cashflow[period_label].astype(str)
    
    #print(cashflow.head())
    
    # Rename the grouping column to a common name "Period"
    #cashflow = cashflow.rename(columns={period_label: "Period"})

    # Melt DataFrame for line plot
    cashflow_melted = cashflow.melt(
        id_vars=period_label,
        value_vars=["Inflow", "Outflow", "NetFlow"],
        var_name="FlowType",
        value_name="Amount"
    )

    # --- Plotly Cashflow Chart ---
    cashflow_fig = px.line(
        cashflow_melted,
        x=period_label,
        y="Amount",
        color="FlowType",
        markers=True,
        title=f"📆 {period_label}ly M-PESA Cash Flow",
        line_dash="FlowType",
        color_discrete_map={
            "Inflow": "green",
            "Outflow": "red",
            "NetFlow": "blue"
        }
    )
    cashflow_fig.update_layout(
        xaxis_title=period_label,
        yaxis_title="Amount (KES)",
        legend_title="Flow Type",
        template="plotly_white",
        title_x=0.5,
        margin=dict(l=40, r=40, t=60, b=40)
    )
    cashflow_fig.update_xaxes(tickangle=45)
    cashflow_graph = json.dumps(cashflow_fig, cls=plotly.utils.PlotlyJSONEncoder)

    # --- Category Trends ---
    def category_trends_over_time(df: pd.DataFrame, period: str = "M"):
        df["Period"] = df["CompletionTime"].dt.to_period(period).astype(str)

        category_trends = (
            df.groupby(["Period", "Category"])
            .agg(
                Total_Spent=("Withdrawn", "sum"),
                Total_Received=("PaidIn", "sum")
            )
            .reset_index()
        )

        category_trends["NetFlow"] = category_trends["Total_Received"] - category_trends["Total_Spent"]

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

        return category_trends, json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

    # --- Merchant Trends ---
    def merchant_trends_over_time(df: pd.DataFrame, period: str = "M"):
        df["Period"] = df["CompletionTime"].dt.to_period(period).astype(str)
        merchant_trends = (
            df.groupby(["Period", "Counterparty"])
            .agg(
                Total_Spent=("Withdrawn", "sum"),
                Total_Received=("PaidIn", "sum")
            )
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

        return merchant_trends, json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

    # --- Generate Graphs Based on Selected Period ---
    category_data, category_graph = category_trends_over_time(filtered_df, period=selected_period)
    merchant_data, merchant_graph = merchant_trends_over_time(filtered_df, period=selected_period)

    # --- Render Template ---
    return render_template(
        'analysis.html',
        title='Analysis',
        form=form,
        selected_period=selected_period,
        cashflow=cashflow.to_dict('records'),
        cashflow_graph=cashflow_graph,
        category_graph=category_graph,
        merchant_graph=merchant_graph
    )

