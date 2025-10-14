from main import db


class mpesaTransaction(db.Model):
    __tablename__ = 'MpesaTransactions'
    receiptNo = db.Column(db.String(20), unique=True, nullable=False)
    completionTime = db.Column(db.DateTime, nullable=False)
    details = db.Column(db.String(255), nullable=False)
    transactionStatus = db.Column(db.String(50), nullable=False)
    paidIn = db.Column(db.Float, nullable=True)
    withdrawn = db.Column(db.Float, nullable=True)
    balance = db.Column(db.Float, nullable=True)
    raw = db.Column(db.Text, nullable=True)
    dateUploaded = db.Column(db.DateTime, nullable=False)
