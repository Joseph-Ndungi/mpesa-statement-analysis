from flask_wtf import FlaskForm
from wtforms import DateField,SelectField, StringField
import json 
from datetime import datetime
from wtforms.validators import InputRequired
import pandas as pd
import numpy as np



#print(data)
class FilterForm(FlaskForm):
    startDate = DateField(default=datetime.strptime('2025-01-01','%Y-%m-%d'),validators=[InputRequired()])
    endDate = DateField(default=datetime.strptime('2025-12-31','%Y-%m-%d'),validators=[InputRequired()])
    #period = SelectField(choices=('Monthly','Weekly'), validators=[InputRequired()])
    period = SelectField(
        'Period',
        choices=[('M', 'Monthly'), ('W', 'Weekly')],
        default='M'
    )
    

class DateForm(FlaskForm):
    startDate = DateField(default=datetime.strptime('2025-01-01','%Y-%m-%d'),validators=[InputRequired()])
    endDate = DateField(default=datetime.strptime('2025-12-31','%Y-%m-%d'),validators=[InputRequired()])
