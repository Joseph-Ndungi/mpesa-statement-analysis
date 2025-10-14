import re
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from datetime import datetime
from PyPDF2 import PdfReader
from PyPDF2.errors import PdfReadError
import io
import csv
import os


@dataclass
class Transaction:
    receipt_no: str
    completion_time: str
    details: str
    transaction_status: str
    paid_in: Optional[float] = None
    withdrawn: Optional[float] = None
    balance: Optional[float] = None
    raw: Optional[str] = None


@dataclass
class MPesaStatement:
    transactions: List[Transaction]

class PdfService:
    # -------------------------------------------------
    # Load PDF safely into memory
    # -------------------------------------------------
    @staticmethod
    def load_pdf(file_path: str) -> Dict[str, Any]:
        """
        Loads a PDF file fully into memory and checks if it's password protected.
        Returns a dict with protection status and PdfReader object.
        """
        try:
            with open(file_path, "rb") as f:
                pdf_bytes = f.read()

            reader = PdfReader(io.BytesIO(pdf_bytes))

            if reader.is_encrypted:
                try:
                    reader.decrypt("")  # Try empty password
                    # Ensure decryption succeeded by accessing first page
                    reader.pages[0]
                    return {"is_protected": False, "pdf": reader}
                except Exception:
                    return {"is_protected": True}
            else:
                return {"is_protected": False, "pdf": reader}

        except PdfReadError as e:
            raise RuntimeError(f"Error reading PDF: {e}")

    # -------------------------------------------------
    # Unlock encrypted PDF
    # -------------------------------------------------
    @staticmethod
    def unlock_pdf(file_path: str, password: str) -> PdfReader:
        """
        Unlocks an encrypted PDF with a provided password and loads it into memory.
        """
        with open(file_path, "rb") as f:
            pdf_bytes = f.read()

        reader = PdfReader(io.BytesIO(pdf_bytes))

        if reader.is_encrypted:
            result = reader.decrypt(password)
            if result == 0:
                raise ValueError("Incorrect password. Please try again.")

        return reader

    # -------------------------------------------------
    # Extract and combine text
    # -------------------------------------------------
    @staticmethod
    def extract_text_from_page(pdf: PdfReader, page_number: int) -> str:
        """
        Extracts text from a specific page and cleans spacing.
        """
        try:
            page = pdf.pages[page_number - 1]
            text = page.extract_text() or ""
        except Exception as e:
            print(f"Error reading page {page_number}: {e}")
            return ""

        text = re.sub(r"[ \t]{5,}", "   ", text)
        return text

    @staticmethod
    def parse_mpesa_statement(pdf: PdfReader) -> "MPesaStatement":
        """
        Combines all text from PDF and parses M-PESA transactions.
        """
        # all_text = ""
        # for i in range(len(pdf.pages)):
        #     page_text = PdfService.extract_text_from_page(pdf, i + 1)
        #     all_text += page_text + "\n"
        all_text = ""
        for i in range(len(pdf.pages)):
            page_text = PdfService.extract_text_from_page(pdf, i + 1)
            all_text += page_text.strip() + "\n\n---PAGEBREAK---\n\n"

        # ✅ Clean up footer text before parsing
        all_text = re.sub(
            r"Disclaimer:.*?(WMF\d{6}GT|Safaricom|Page\s+\d+\s+of\s+\d+)",
            "",
            all_text,
            flags=re.S
        )


        transactions = PdfService.parse_transactions(all_text)
        return MPesaStatement(transactions)

    # -------------------------------------------------
    # Transaction parsing
    # -------------------------------------------------
    @staticmethod
    def parse_transactions(text: str) -> List[Transaction]:
        transactions = []

        # Try to locate the start of detailed transactions
        patterns = [
            r"DETAILED\s+STATEMENT[\s\S]*?(?:Receipt\s+No\.|Receipt\s*Number)",
            r"DETAILED\s+STATEMENT[\s\S]*?(?:[A-Z0-9]{10})",
            r"Receipt\s+No\s+Completion\s+Time\s+Details",
            r"[A-Z0-9]{10}\s+\d{4}-\d{2}-\d{2}",
        ]

        detailed_section = ""
        for p in patterns:
            match = re.search(p, text, re.I)
            if match:
                detailed_section = text[match.start():]
                break
        if not detailed_section:
            detailed_section = text

        # Identify transaction blocks by receipt numbers
        receipt_pattern = re.compile(
            r"(?:^|\n)([A-Z0-9]{10})\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})"
        )
        matches = list(receipt_pattern.finditer(detailed_section))
        blocks = []
        for i, m in enumerate(matches):
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(detailed_section)
            block = detailed_section[start:end].strip()
            if "Disclaimer:" not in block:
                blocks.append(block)

        # Parse each transaction block
        for block in blocks:
            t = PdfService._parse_transaction_block(block)
            if t:
                transactions.append(t)

        # Sort by date/time
        def safe_parse_date(dt):
            try:
                return datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")
            except Exception:
                return datetime.min

        transactions.sort(key=lambda tr: safe_parse_date(tr.completion_time))
        return transactions

    @staticmethod
    def _parse_transaction_block(block: str) -> Optional[Transaction]:
        # Extract receipt number
        receipt_match = re.search(r"\b([A-Z0-9]{10})\b", block)
        if not receipt_match:
            return None
        receipt_no = receipt_match.group(1)

        # Extract completion time
        date_match = re.search(r"\d{4}-\d{2}-\d{2}", block)
        time_match = re.search(r"\d{2}:\d{2}:\d{2}", block)
        completion_time = f"{date_match.group()} {time_match.group()}" if (date_match and time_match) else ""
        
        # Fix: restore line break before "Completed/Failed/Pending" if it was merged with details
        block = re.sub(r"(?i)(?<=\w)(COMPLETED|FAILED|PENDING)", r"\n\1", block)

        # Detect status
        status_match = re.search(r"(?i)\b(COMPLETED|FAILED|PENDING)\b", block)
        status = status_match.group(1).capitalize() if status_match else "Unknown"
        
        # Amount extraction
        # Find all monetary amounts, keeping sign
        amount_matches = re.findall(r"-?[\d,]+\.\d{2}", block)
        amounts = [PdfService.parse_amount(a) for a in amount_matches]

        paid_in, withdrawn, balance = None, None, None

        if amounts:
            balance = amounts[-1]  # Last number is almost always the balance
            # Look for any negatives before that (withdrawals)
            negatives = [a for a in amounts[:-1] if a < 0]
            positives = [a for a in amounts[:-1] if a > 0]
            withdrawn = negatives[-1] if negatives else None
            paid_in = positives[-1] if positives else None

        # Clean details
        details = block
        for pattern in [
            re.escape(receipt_no),
            r"\d{4}-\d{2}-\d{2}",
            r"\d{2}:\d{2}:\d{2}",
            r"-?[\d,]+\.\d{2}",
            r"(?i)\b(COMPLETED|FAILED|PENDING)\b",
        ]:
            details = re.sub(pattern, "", details)
        details = re.sub(r"\s+", " ", details).strip()

        return Transaction(
            receipt_no=receipt_no,
            completion_time=completion_time,
            details=details,
            transaction_status=status,
            paid_in=paid_in,
            withdrawn=withdrawn,
            balance=balance or 0,
            raw=block,
        )


    # -------------------------------------------------
    # Utility
    # -------------------------------------------------
    @staticmethod
    def parse_amount(amount_str: str) -> float:
        if not amount_str or amount_str == "-":
            return 0.0
        try:
            cleaned = re.sub(r"[^\d.-]", "", amount_str)
            parts = cleaned.split(".")
            if len(parts) > 2:
                cleaned = f"{parts[0]}.{''.join(parts[1:])}"
            return float(cleaned)
        except ValueError:
            return 0.0



if __name__ == "__main__":
    pdf_path = input("Enter path to M-PESA statement PDF: ").strip()
    result = PdfService.load_pdf(pdf_path)

    if result["is_protected"]:
        print("PDF is password protected.")
        pwd = input("Enter password: ")
        pdf = PdfService.unlock_pdf(pdf_path, pwd)
    else:
        pdf = result["pdf"]

    statement = PdfService.parse_mpesa_statement(pdf)
    print(f"\n✅ Parsed {len(statement.transactions)} transactions\n")

    # Preview first 10
    for tx in statement.transactions[:10]:
        print(f"{tx.receipt_no} | {tx.completion_time} | {tx.details[:60]}...")

    # -------------------------------------------------
    # Export to CSV
    # -------------------------------------------------
    output_file = os.path.splitext(pdf_path)[0] + "_transactions6.csv"
    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["ReceiptNo", "CompletionTime", "Details", "Status", "PaidIn", "Withdrawn", "Balance", "Raw"])

        for tx in statement.transactions:
            writer.writerow([
                tx.receipt_no,
                tx.completion_time,
                tx.details,
                tx.transaction_status,
                tx.paid_in,
                tx.withdrawn,
                tx.balance,
                tx.raw,
            ])

    print(f"\n📁 CSV exported successfully to: {output_file}")
