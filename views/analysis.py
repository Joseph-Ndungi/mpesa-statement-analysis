from flask import render_template, request, redirect, url_for, flash, Blueprint
from forms import *

analysisBp = Blueprint('analysisBp', __name__)