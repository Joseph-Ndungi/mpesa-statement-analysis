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
    
    paidInTotal = df["PaidIn"].sum()
    withdrawnTotal = df["Withdrawn"].sum()
    
    netFlow = paidInTotal - withdrawnTotal
    averageTransactionValue = df["PaidIn"].mean() / df["Withdrawn"].mean()
    transactionCount = len(df)
    
    #extract month and week features
    df["Date"] = df["CompletionTime"].dt.date
    df["Month"] = df["CompletionTime"].dt.to_period("M").astype(str)
    df["Week"] = df["CompletionTime"].dt.to_period("W").astype(str)
    
    # --- Compute monthly totals ---
    monthly_trends = (
        df.groupby("Month")[["PaidIn", "Withdrawn"]]
        .sum()
        .reset_index()
        .sort_values("Month")
    )

    # --- Compute weekly totals ---
    weekly_trends = (
        df.groupby("Week")[["PaidIn", "Withdrawn"]]
        .sum()
        .reset_index()
        .sort_values("Week")
    )
    
        # --- Compute daily inflow/outflow ---
    daily_trends = (
        df.groupby("Date")[["PaidIn", "Withdrawn"]]
        .sum()
        .reset_index()
        .sort_values("Date")
    )
    
    return render_template('summary.html',
                           title='Summary', form=form, paidInTotal=paidInTotal,
                           withdrawnTotal=withdrawnTotal, netFlow=netFlow,
                           averageTransactionValue=averageTransactionValue,
                           transactionCount=transactionCount,
                           monthly_trends=monthly_trends.to_dict('records'),
                           weekly_trends=weekly_trends.to_dict('records'),
                           daily_trends=daily_trends.to_dict('records'))