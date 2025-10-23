from flask import render_template, request, redirect, url_for, flash, Blueprint
from forms import *
import pandas as pd
import matplotlib.pyplot as plt
import re
import glob
import os
from datetime import date, datetime

summaryBp = Blueprint('summaryBp', __name__)
folderPath = 'uploads/'
csvFiles = glob.glob(os.path.join(folderPath, '*.csv'))


@summaryBp.route('/summary', methods=['GET', 'POST'])
def summary():
    form = DateForm()

    # --- Default configuration ---
    default_start = date(2025, 7, 15)
    default_end = date(2025, 7, 27)

    # --- Determine whether to use defaults or submitted form ---
    if request.method == "POST" and form.validate_on_submit():
        start_date = form.startDate.data or default_start
        end_date = form.endDate.data or default_end
    else:
        start_date = default_start
        end_date = default_end
        form.startDate.data = default_start
        form.endDate.data = default_end

    # --- Load uploaded CSVs safely ---
    uploads_dir = os.path.join(os.getcwd(), "uploads")

    try:
        csv_files = [
            os.path.join(uploads_dir, f)
            for f in os.listdir(uploads_dir)
            if f.endswith(".csv")
        ]
    except FileNotFoundError:
        flash("⚠️ 'uploads' directory not found.", "danger")
        return render_template(
            'summary.html',
            title='Summary',
            form=form,
            paidInTotal=0,
            withdrawnTotal=0,
            netFlow=0,
            averageTransactionValue=0,
            transactionCount=0,
            monthly_trends=[],
            weekly_trends=[],
            daily_trends=[]
        )

    if not csv_files:
        flash("⚠️ No transaction CSVs found in uploads directory.", "warning")
        return render_template(
            'summary.html',
            title='Summary',
            form=form,
            paidInTotal=0,
            withdrawnTotal=0,
            netFlow=0,
            averageTransactionValue=0,
            transactionCount=0,
            monthly_trends=[],
            weekly_trends=[],
            daily_trends=[]
        )

    # --- Read and combine all CSVs into one DataFrame ---
    try:
        df_list = [pd.read_csv(file, parse_dates=['CompletionTime']) for file in csv_files]
        df = pd.concat(df_list, ignore_index=True)
    except Exception as e:
        flash(f"⚠️ Error reading CSV files: {str(e)}", "danger")
        return render_template(
            'summary.html',
            title='Summary',
            form=form,
            paidInTotal=0,
            withdrawnTotal=0,
            netFlow=0,
            averageTransactionValue=0,
            transactionCount=0,
            monthly_trends=[],
            weekly_trends=[],
            daily_trends=[]
        )

    # --- Clean numeric columns ---
    df["Withdrawn"] = pd.to_numeric(df["Withdrawn"], errors="coerce").abs().fillna(0)
    df["PaidIn"] = pd.to_numeric(df["PaidIn"], errors="coerce").fillna(0)

    # --- Apply date filters ---
    filtered_df = df[
        (df["CompletionTime"] >= pd.Timestamp(start_date)) &
        (df["CompletionTime"] <= pd.Timestamp(end_date))
    ]

    # --- Handle case where no data after filtering ---
    if filtered_df.empty:
        flash("⚠️ No transactions found for the selected date range.", "warning")
        return render_template(
            'summary.html',
            title='Summary',
            form=form,
            paidInTotal=0,
            withdrawnTotal=0,
            netFlow=0,
            averageTransactionValue=0,
            transactionCount=0,
            monthly_trends=[],
            weekly_trends=[],
            daily_trends=[]
        )

    # --- Summary Metrics ---
    paidInTotal = filtered_df["PaidIn"].sum()
    withdrawnTotal = filtered_df["Withdrawn"].sum()
    netFlow = paidInTotal - withdrawnTotal
    transactionCount = len(filtered_df)

    # Avoid division by zero
    if transactionCount > 0:
        averageTransactionValue = (paidInTotal + withdrawnTotal) / transactionCount
    else:
        averageTransactionValue = 0

    # --- Extract date features ---
    filtered_df["Date"] = filtered_df["CompletionTime"].dt.date
    filtered_df["Month"] = filtered_df["CompletionTime"].dt.to_period("M").astype(str)
    filtered_df["Week"] = filtered_df["CompletionTime"].dt.to_period("W").astype(str)

    # --- Compute Daily / Weekly / Monthly Trends ---
    daily_trends = (
        filtered_df.groupby("Date")[["PaidIn", "Withdrawn"]]
        .sum()
        .reset_index()
        .sort_values("Date")
    )

    weekly_trends = (
        filtered_df.groupby("Week")[["PaidIn", "Withdrawn"]]
        .sum()
        .reset_index()
        .sort_values("Week")
    )

    monthly_trends = (
        filtered_df.groupby("Month")[["PaidIn", "Withdrawn"]]
        .sum()
        .reset_index()
        .sort_values("Month")
    )

    # --- Render Template ---
    return render_template(
        'summary.html',
        title='Summary',
        form=form,
        paidInTotal=paidInTotal,
        withdrawnTotal=withdrawnTotal,
        netFlow=netFlow,
        averageTransactionValue=averageTransactionValue,
        transactionCount=transactionCount,
        monthly_trends=monthly_trends.to_dict('records'),
        weekly_trends=weekly_trends.to_dict('records'),
        daily_trends=daily_trends.to_dict('records')
    )

