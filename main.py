import os
from dotenv import load_dotenv
from flask import Flask


load_dotenv()


def create_app():
    app = Flask(__name__)
    app.secret_key = os.getenv("SECRET_KEY")
    
    #register blueprints
    from views.analysis import analysisBp
    from views.insights import insightsBp
    from views.summary import summaryBp

    app.register_blueprint(analysisBp)
    app.register_blueprint(insightsBp)
    app.register_blueprint(summaryBp)

    return app
