import pandas as pd
import matplotlib.pyplot as plt
import re

df = pd.read_csv("MPESA_Statement_2025-10-10_to_2025-07-10_2547xxxxxx604_transactions6.csv", parse_dates=["CompletionTime"])
# df["PaidIn"] = pd.to_numeric(df["PaidIn"], errors="coerce").fillna(0)
# df["Withdrawn"] = pd.to_numeric(df["Withdrawn"], errors="coerce").fillna(0)


#summary stats
paidInTotal = df["PaidIn"].sum()
#withdrawn is negated to reflect outflow, just work with absolute values
df["Withdrawn"] = df["Withdrawn"].abs()
withdrawnTotal = df["Withdrawn"].sum()
netFlow = paidInTotal - withdrawnTotal
averageTransactionValue = df["PaidIn"].mean() / df["Withdrawn"].mean()
transactionCount = len(df)

allAmounts = pd.concat([df["PaidIn"], df["Withdrawn"].abs()])
averageAmount = allAmounts.mean()
medianAmount = allAmounts.median()



#time based analysis
# Ensure datetime type
df["CompletionTime"] = pd.to_datetime(df["CompletionTime"], errors="coerce")

# --- Extract time features ---
df["Date"] = df["CompletionTime"].dt.date
df["Month"] = df["CompletionTime"].dt.to_period("M").astype(str)
df["Week"] = df["CompletionTime"].dt.to_period("W").astype(str)

# --- Compute daily inflow/outflow ---
daily_trends = (
    df.groupby("Date")[["PaidIn", "Withdrawn"]]
    .sum()
    .reset_index()
    .sort_values("Date")
)

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

# --- Plot daily inflow vs outflow ---
plt.figure(figsize=(10, 5))
plt.plot(daily_trends["Date"], daily_trends["PaidIn"], label="Paid In", linewidth=2)
plt.plot(daily_trends["Date"], daily_trends["Withdrawn"], label="Withdrawn", linewidth=2)
plt.title("🗓️ Daily Inflow vs Outflow")
plt.xlabel("Date")
plt.ylabel("Amount (KES)")
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.show()

# --- Summary stats ---
print("\n🗓️ TIME-BASED TRENDS SUMMARY")
print("-" * 45)
print(f"Days covered         : {daily_trends['Date'].nunique()}")
print(f"First transaction    : {df['Date'].min()}")
print(f"Last transaction     : {df['Date'].max()}")
print(f"Monthly avg inflow   : KES {monthly_trends['PaidIn'].mean():,.2f}")
print(f"Monthly avg outflow  : KES {monthly_trends['Withdrawn'].mean():,.2f}")
print(f"Weekly avg inflow    : KES {weekly_trends['PaidIn'].mean():,.2f}")
print(f"Weekly avg outflow   : KES {weekly_trends['Withdrawn'].mean():,.2f}")
print("-" * 45)

trend_summary = {
    "days_covered": daily_trends["Date"].nunique(),
    "first_txn": str(df["Date"].min()),
    "last_txn": str(df["Date"].max()),
    "monthly_avg_inflow": monthly_trends["PaidIn"].mean(),
    "monthly_avg_outflow": monthly_trends["Withdrawn"].mean(),
    "weekly_avg_inflow": weekly_trends["PaidIn"].mean(),
    "weekly_avg_outflow": weekly_trends["Withdrawn"].mean(),
}

#CATEGORY BREAKDOWN
# --- Categorize each transaction from the "Details" text ---
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

# --- Group by category ---
category_summary = (
    df.groupby("Category")[["PaidIn", "Withdrawn"]]
    .sum()
    .reset_index()
    .sort_values("Withdrawn", ascending=False)
)

# --- Add net effect column ---
category_summary["Net (In - Out)"] = category_summary["PaidIn"] - category_summary["Withdrawn"]

print("🏦 CATEGORY BREAKDOWN SUMMARY")
print("-" * 50)
print(category_summary)

# --- Plot inflow/outflow by category ---
plt.figure(figsize=(10, 6))
category_summary.plot(
    x="Category", 
    y=["PaidIn", "Withdrawn"], 
    kind="bar", 
    figsize=(10,6)
)
plt.title("🏦 Inflow vs Outflow by Category")
plt.xlabel("Transaction Category")
plt.ylabel("Amount (KES)")
plt.xticks(rotation=45, ha="right")
plt.tight_layout()
plt.show()


#top counterparties/merchants
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

top_counterparties_count = (
    df["Counterparty"].value_counts().head(10).reset_index()
)
top_counterparties_count.columns = ["Counterparty", "Count"]

print("🔝 Top 10 Most Frequent Counterparties:")
print(top_counterparties_count)

df["NetAmount"] = df["PaidIn"].fillna(0) - df["Withdrawn"].fillna(0)

top_counterparties_value = (
    df.groupby("Counterparty")["NetAmount"].sum()
    .abs()
    .sort_values(ascending=False)
    .head(10)
    .reset_index()
)

print("💰 Top 10 Counterparties by Total Transaction Value:")
print(top_counterparties_value)



plt.figure(figsize=(10, 5))
plt.barh(top_counterparties_value["Counterparty"], top_counterparties_value["NetAmount"])
plt.title("Top 10 Counterparties by Transaction Value")
plt.xlabel("Total Amount (KES)")
plt.gca().invert_yaxis()
plt.show()


#monthly and weekly cash flow analysis
df["Month"] = df["CompletionTime"].dt.to_period("M")

cashflow = df.groupby("Month").agg(
    Inflow=("PaidIn", "sum"),
    Outflow=("Withdrawn", "sum")
).reset_index()

cashflow["NetFlow"] = cashflow["Inflow"] - cashflow["Outflow"]
cashflow["Month"] = cashflow["Month"].astype(str)

print("📆 Monthly Cash Flow Summary:")
print(cashflow)


#weekly
df["Week"] = df["CompletionTime"].dt.to_period("W")
cashflow_weekly = df.groupby("Week").agg(
    Inflow=("PaidIn", "sum"),
    Outflow=("Withdrawn", "sum")
).reset_index()
cashflow_weekly["NetFlow"] = cashflow_weekly["Inflow"] - cashflow_weekly["Outflow"]


plt.figure(figsize=(10, 6))
plt.plot(cashflow["Month"], cashflow["Inflow"], label="Inflow (KES)", marker="o", color="green")
plt.plot(cashflow["Month"], cashflow["Outflow"], label="Outflow (KES)", marker="o", color="red")
plt.plot(cashflow["Month"], cashflow["NetFlow"], label="Net Flow (KES)", marker="o", color="blue", linestyle="--")

plt.title("📆 Monthly M-PESA Cash Flow")
plt.xlabel("Month")
plt.ylabel("Amount (KES)")
plt.xticks(rotation=45)
plt.legend()
plt.grid(alpha=0.3)
plt.tight_layout()
plt.show()


#Highlight Key Insights
most_profitable = cashflow.loc[cashflow["NetFlow"].idxmax()]
most_expensive = cashflow.loc[cashflow["NetFlow"].idxmin()]

print(f"💰 Highest Net Inflow: {most_profitable['Month']} (+{most_profitable['NetFlow']:.2f} KES)")
print(f"📉 Highest Net Outflow: {most_expensive['Month']} ({most_expensive['NetFlow']:.2f} KES)")


#Category & Merchant Trends — Weekly + Monthly Version

def category_trends_over_time(df: pd.DataFrame, period: str = "M"):
    """
    Analyzes M-PESA spending trends by category over time.

    Args:
        df (pd.DataFrame): The transaction data.
        period (str): "M" for monthly or "W" for weekly.
    """
    if "CompletionTime" not in df.columns:
        raise ValueError("Expected 'CompletionTime' column in DataFrame")

    # Add period column dynamically
    df["Period"] = df["CompletionTime"].dt.to_period(period)

    # Aggregate totals by period and category
    category_trends = (
        df.groupby(["Period", "Category"])
        .agg(
            Total_Spent=("Withdrawn", "sum"),
            Total_Received=("PaidIn", "sum")
        )
        .reset_index()
    )

    # Net flow (received - spent)
    category_trends["NetFlow"] = category_trends["Total_Received"] - category_trends["Total_Spent"]

    # Identify top 5 spending categories overall
    top_categories = (
        df.groupby("Category")["Withdrawn"]
        .sum()
        .sort_values(ascending=False)
        .head(5)
        .index
    )

    plot_data = category_trends[category_trends["Category"].isin(top_categories)]

    # Visualization
    plt.figure(figsize=(10, 6))
    for cat in top_categories:
        data = plot_data[plot_data["Category"] == cat]
        plt.plot(
            data["Period"].astype(str),
            data["Total_Spent"],
            marker="o",
            label=cat
        )

    label = "Monthly" if period == "M" else "Weekly"
    plt.title(f"📊 {label} Spending Trends by Category")
    plt.xlabel(label)
    plt.ylabel("Total Spent (KES)")
    plt.xticks(rotation=45)
    plt.legend()
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.show()

    return category_trends

def merchant_trends_over_time(df: pd.DataFrame, period: str = "M"):
    """
    Tracks spending trends for top merchants/counterparties.
    """
    if "CompletionTime" not in df.columns or "Counterparty" not in df.columns:
        raise ValueError("Expected 'CompletionTime' and 'Counterparty' columns in DataFrame")

    df["Period"] = df["CompletionTime"].dt.to_period(period)

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

    plt.figure(figsize=(10, 6))
    for merchant in top_merchants:
        data = plot_data[plot_data["Counterparty"] == merchant]
        plt.plot(
            data["Period"].astype(str),
            data["Total_Spent"],
            marker="o",
            label=merchant
        )

    label = "Monthly" if period == "M" else "Weekly"
    plt.title(f"🏪 {label} Spending by Top Merchants")
    plt.xlabel(label)
    plt.ylabel("Total Spent (KES)")
    plt.xticks(rotation=45)
    plt.legend()
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.show()

    return merchant_trends

# --- Monthly trends ---
category_monthly = category_trends_over_time(df, period="M")
merchant_monthly = merchant_trends_over_time(df, period="M")

# --- Weekly trends ---
category_weekly = category_trends_over_time(df, period="W")
merchant_weekly = merchant_trends_over_time(df, period="W")


#balance evolution
def plot_balance_evolution(df: pd.DataFrame):
    """
    Plots the cumulative balance evolution of M-PESA over time.
    """
    if "CompletionTime" not in df.columns:
        raise ValueError("Expected 'CompletionTime' column in DataFrame")

    # Sort by date to ensure correct chronological flow
    df = df.sort_values("CompletionTime")

    # Ensure numeric columns
    df["PaidIn"] = pd.to_numeric(df["PaidIn"], errors="coerce").fillna(0)
    df["Withdrawn"] = pd.to_numeric(df["Withdrawn"], errors="coerce").fillna(0)

    # Compute net flow and cumulative balance
    df["NetFlow"] = df["PaidIn"] - df["Withdrawn"]
    df["CumulativeBalance"] = df["NetFlow"].cumsum()

    # Optional: include original "Balance" column if present
    if "Balance" in df.columns and df["Balance"].notnull().any():
        df["Balance"] = pd.to_numeric(df["Balance"], errors="coerce")
        df["Balance"].fillna(method="ffill", inplace=True)
        df["Balance"] = df["Balance"].fillna(df["CumulativeBalance"])

    # --- Plot ---
    plt.figure(figsize=(12, 6))
    plt.plot(df["CompletionTime"], df["CumulativeBalance"], label="Cumulative Net Flow", linewidth=2)
    
    if "Balance" in df.columns:
        plt.plot(df["CompletionTime"], df["Balance"], linestyle="--", alpha=0.7, label="Reported Balance")

    plt.title("💰 M-PESA Balance Evolution Over Time")
    plt.xlabel("Date")
    plt.ylabel("Balance (KES)")
    plt.grid(alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.show()

    # Summary stats
    total_in = df["PaidIn"].sum()
    total_out = df["Withdrawn"].sum()
    net_flow = total_in - total_out
    peak_balance = df["CumulativeBalance"].max()
    lowest_balance = df["CumulativeBalance"].min()

    summary = {
        "Total Paid In": total_in,
        "Total Withdrawn": total_out,
        "Net Flow": net_flow,
        "Peak Balance (Calculated)": peak_balance,
        "Lowest Balance (Calculated)": lowest_balance,
    }

    print("\n💡 Balance Summary:")
    for k, v in summary.items():
        print(f"{k}: {v:,.2f}")

    return df, summary


df, summary = plot_balance_evolution(df)


#spending efficiency & insights
def spending_efficiency_metrics(df: pd.DataFrame):
    """
    Analyze spending and inflow/outflow efficiency from M-PESA statement.
    """
    df["PaidIn"] = pd.to_numeric(df["PaidIn"], errors="coerce").fillna(0)
    df["Withdrawn"] = pd.to_numeric(df["Withdrawn"], errors="coerce").fillna(0)

    total_in = df["PaidIn"].sum()
    total_out = df["Withdrawn"].sum()
    net_flow = total_in - total_out

    # --- Ratios ---
    savings_ratio = (net_flow / total_in) * 100 if total_in > 0 else 0
    expense_ratio = (total_out / total_in) * 100 if total_in > 0 else 0
    avg_transaction_in = df.loc[df["PaidIn"] > 0, "PaidIn"].mean()
    avg_transaction_out = df.loc[df["Withdrawn"] > 0, "Withdrawn"].mean()

    efficiency_summary = {
        "Total Inflows": total_in,
        "Total Outflows": total_out,
        "Net Flow": net_flow,
        "Savings Ratio (%)": savings_ratio,
        "Expense Ratio (%)": expense_ratio,
        "Average Deposit": avg_transaction_in,
        "Average Spend": avg_transaction_out,
        "Transaction Count": len(df),
    }

    print("\n📊 Spending Efficiency Summary:")
    for k, v in efficiency_summary.items():
        print(f"{k:25s}: {v:,.2f}")

    return efficiency_summary

def spending_trends_over_time(df: pd.DataFrame, freq="M"):
    """
    Plot inflows vs outflows and compute monthly/weekly net flow ratios.
    freq = "M" (monthly) or "W" (weekly)
    """
    df["PaidIn"] = pd.to_numeric(df["PaidIn"], errors="coerce").fillna(0)
    df["Withdrawn"] = pd.to_numeric(df["Withdrawn"], errors="coerce").fillna(0)
    df = df.sort_values("CompletionTime")

    grouped = (
        df.resample(freq, on="CompletionTime")[["PaidIn", "Withdrawn"]]
        .sum()
        .assign(NetFlow=lambda x: x["PaidIn"] - x["Withdrawn"])
    )

    # Compute ratios
    grouped["SavingsRatio"] = (grouped["NetFlow"] / grouped["PaidIn"].replace(0, pd.NA)) * 100

    # --- Plot ---
    plt.figure(figsize=(12, 6))
    plt.plot(grouped.index, grouped["PaidIn"], label="Inflows", linewidth=2)
    plt.plot(grouped.index, grouped["Withdrawn"], label="Outflows", linewidth=2)
    plt.fill_between(grouped.index, grouped["PaidIn"], grouped["Withdrawn"], alpha=0.2)
    plt.title(f"💡 Spending vs Income ({'Monthly' if freq=='M' else 'Weekly'})")
    plt.xlabel("Date")
    plt.ylabel("Amount (KES)")
    plt.legend()
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.show()

    print("\n📅 Period Efficiency Ratios:")
    print(grouped[["PaidIn", "Withdrawn", "NetFlow", "SavingsRatio"]])

    return grouped


efficiency_summary = spending_efficiency_metrics(df)
spending_trends = spending_trends_over_time(df, freq="M")  # or "M"
