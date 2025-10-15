from flask import render_template, request, redirect, url_for, flash, Blueprint
import plotly
from forms import *
import glob
import os
import matplotlib.pyplot as plt
import pandas as pd
import re
import plotly.express as px

trendsBp = Blueprint('trendsBp', __name__)

# folderPath = 'uploads/'

# csvFiles = glob.glob(os.path.join(folderPath, '*.csv'))


# # Read and combine all CSVs into one DataFrame
# dfList = []
# for file in csvFiles:
#     tempDf = pd.read_csv(file, parse_dates=['CompletionTime'])
#     dfList.append(tempDf)

# # Concatenate all data into a single DataFrame
# df = pd.concat(dfList, ignore_index=True)
# # Drop duplicate transactions based on unique ReceiptNo
# df = df.drop_duplicates(subset=["ReceiptNo"], keep="first").reset_index(drop=True)
# df["Withdrawn"] = df["Withdrawn"].abs()


# --- 1. BALANCE EVOLUTION ---
def plot_balance_evolution(df: pd.DataFrame):
    """
    Plots cumulative balance evolution of M-PESA over time (Plotly version).
    Returns a JSON-encoded Plotly figure and summary stats.
    """
    if "CompletionTime" not in df.columns:
        raise ValueError("Expected 'CompletionTime' column in DataFrame")

    # Sort and clean numeric fields
    df = df.sort_values("CompletionTime")
    df["PaidIn"] = pd.to_numeric(df["PaidIn"], errors="coerce").fillna(0)
    df["Withdrawn"] = pd.to_numeric(df["Withdrawn"], errors="coerce").fillna(0)

    # Compute net and cumulative balance
    df["NetFlow"] = df["PaidIn"] - df["Withdrawn"]
    df["CumulativeBalance"] = df["NetFlow"].cumsum()

    # Fill in reported balance if present
    if "Balance" in df.columns:
        df["Balance"] = pd.to_numeric(df["Balance"], errors="coerce")
        df["Balance"].fillna(method="ffill", inplace=True)
        df["Balance"].fillna(df["CumulativeBalance"], inplace=True)

    # --- Summary stats ---
    summary = {
        "Total Paid In": df["PaidIn"].sum(),
        "Total Withdrawn": df["Withdrawn"].sum(),
        "Net Flow": df["PaidIn"].sum() - df["Withdrawn"].sum(),
        "Peak Balance (Calculated)": df["CumulativeBalance"].max(),
        "Lowest Balance (Calculated)": df["CumulativeBalance"].min(),
    }

    # --- Plotly Figure ---
    fig = px.line(
        df,
        x="CompletionTime",
        y=["CumulativeBalance", "Balance"] if "Balance" in df.columns else ["CumulativeBalance"],
        labels={"value": "Balance (KES)", "CompletionTime": "Date", "variable": "Metric"},
        title="💰 M-PESA Balance Evolution Over Time",
        markers=True
    )

    fig.update_layout(template="plotly_white", legend_title_text="Metric")
    fig_json = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

    return fig_json, summary


# --- 2. SPENDING EFFICIENCY ---
def spending_efficiency_metrics(df: pd.DataFrame):
    """
    Calculates spending efficiency and inflow/outflow ratios.
    Returns a summary dictionary.
    """
    df["PaidIn"] = pd.to_numeric(df["PaidIn"], errors="coerce").fillna(0)
    df["Withdrawn"] = pd.to_numeric(df["Withdrawn"], errors="coerce").fillna(0)

    total_in = df["PaidIn"].sum()
    total_out = df["Withdrawn"].sum()
    net_flow = total_in - total_out

    savings_ratio = (net_flow / total_in) * 100 if total_in > 0 else 0
    expense_ratio = (total_out / total_in) * 100 if total_in > 0 else 0

    return {
        "Total Inflows": total_in,
        "Total Outflows": total_out,
        "Net Flow": net_flow,
        "Savings Ratio (%)": savings_ratio,
        "Expense Ratio (%)": expense_ratio,
        "Average Deposit": df.loc[df["PaidIn"] > 0, "PaidIn"].mean(),
        "Average Spend": df.loc[df["Withdrawn"] > 0, "Withdrawn"].mean(),
        "Transaction Count": len(df),
    }


# --- 3. SPENDING TRENDS (Monthly / Weekly) ---
def spending_trends_over_time(df: pd.DataFrame, freq="M"):
    """
    Generates Plotly figure for inflow/outflow trends (Monthly or Weekly).
    Returns JSON-encoded Plotly figure and grouped DataFrame.
    """
    df["PaidIn"] = pd.to_numeric(df["PaidIn"], errors="coerce").fillna(0)
    df["Withdrawn"] = pd.to_numeric(df["Withdrawn"], errors="coerce").fillna(0)
    df = df.sort_values("CompletionTime")

    # Group by time period
    grouped = (
        df.resample(freq, on="CompletionTime")[["PaidIn", "Withdrawn"]]
        .sum()
        .assign(NetFlow=lambda x: x["PaidIn"] - x["Withdrawn"])
        .reset_index()
    )

    label = "Monthly" if freq == "M" else "Weekly"

    # --- Plotly Figure ---
    fig = px.line(
        grouped,
        x="CompletionTime",
        y=["PaidIn", "Withdrawn", "NetFlow"],
        labels={"value": "Amount (KES)", "variable": "Flow Type", "CompletionTime": "Date"},
        title=f"💡 {label} Spending Trends (Inflow vs Outflow)",
        markers=True
    )

    fig.update_layout(template="plotly_white", legend_title_text="Flow Type")
    fig_json = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

    return fig_json, grouped

@trendsBp.route("/trends", methods=["GET", "POST"])
def trends():
    form = FilterForm()
    period = "M"  # Default to monthly
    balance_plot = None
    spending_plot = None
    balance_summary = None
    efficiency_summary = None

    if request.method == "POST" and form.validate_on_submit():
        start_date = form.startDate.data
        end_date = form.endDate.data
        period = form.period.data or "M"

        # --- Load all uploaded CSVs ---
        uploads_dir = os.path.join(os.getcwd(), "uploads")
        csv_files = [
            os.path.join(uploads_dir, f)
            for f in os.listdir(uploads_dir)
            if f.endswith(".csv")
        ]

        if not csv_files:
            flash("⚠️ No transaction CSVs found in uploads directory.", "warning")
            return redirect(request.url)

        # --- Read and combine CSVs ---
        df_list = [pd.read_csv(f, parse_dates=["CompletionTime"]) for f in csv_files]
        df = pd.concat(df_list, ignore_index=True)

        # Drop duplicates based on ReceiptNo
        #df = df.drop_duplicates(subset=["ReceiptNo"], keep="first")

        # Filter by selected date range if provided
        if start_date and end_date:
            df = df[(df["CompletionTime"] >= pd.Timestamp(start_date)) & (df["CompletionTime"] <= pd.Timestamp(end_date))]
        elif start_date:
            df = df[df["CompletionTime"] >= pd.Timestamp(start_date)]
        elif end_date:
            df = df[df["CompletionTime"] <= pd.Timestamp(end_date)]

        # Ensure Withdrawn column is positive for analysis
        df["Withdrawn"] = df["Withdrawn"].abs()

        if df.empty:
            flash("⚠️ No transactions found in the selected date range.", "warning")
            return redirect(request.url)

        # --- Run analytics ---
        balance_plot, balance_summary = plot_balance_evolution(df)
        efficiency_summary = spending_efficiency_metrics(df)
        spending_plot, _ = spending_trends_over_time(df, freq=period)
        
        #print (balance_summary)
        #print (efficiency_summary)


    # --- Render results ---
    return render_template(
        "trends.html",
        form=form,
        period=period,
        balance_plot=balance_plot,
        balance_summary=balance_summary,
        efficiency_summary=efficiency_summary,
        spending_plot=spending_plot,
        title="Trends",
    )

