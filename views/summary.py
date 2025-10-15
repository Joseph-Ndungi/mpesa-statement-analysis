from flask import render_template, request, redirect, url_for, flash, Blueprint
from forms import *
import pandas as pd
import matplotlib.pyplot as plt
import re

summaryBp = Blueprint('summaryBp', __name__)

df = pd.read_csv('uploads/MPESA_Statement_2025-10-10_to_2025-07-10_2547xxxxxx604_transactions.csv', parse_dates=['CompletionTime'])

df["PaidIn"] = pd.to_numeric(df["PaidIn"], errors="coerce").fillna(0)
df["Withdrawn"] = pd.to_numeric(df["Withdrawn"], errors="coerce").fillna(0)
df["Withdrawn"] = df["Withdrawn"].abs()

@summaryBp.route('/summary', methods=['GET', 'POST'])
def summary():
    form = DateForm()

    # --- Base DataFrame ---
    filtered_df = df.copy()

    # --- If form is submitted, apply date filters ---
    if request.method == 'POST' and form.validate_on_submit():
        startDate = form.startDate.data
        endDate = form.endDate.data

        if startDate and endDate:
            mask = (filtered_df["CompletionTime"].dt.date >= startDate) & (
                filtered_df["CompletionTime"].dt.date <= endDate
            )
            filtered_df = filtered_df.loc[mask]
        elif startDate:
            filtered_df = filtered_df.loc[filtered_df["CompletionTime"].dt.date >= startDate]
        elif endDate:
            filtered_df = filtered_df.loc[filtered_df["CompletionTime"].dt.date <= endDate]

    # --- Handle case where no data after filtering ---
    if filtered_df.empty:
        flash("No transactions found for the selected date range.", "warning")
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
    if withdrawnTotal != 0:
        averageTransactionValue = (paidInTotal + withdrawnTotal) / transactionCount
    else:
        averageTransactionValue = paidInTotal / transactionCount if transactionCount > 0 else 0

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
