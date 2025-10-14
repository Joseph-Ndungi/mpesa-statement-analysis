from flask import render_template, request, redirect, url_for, flash, Blueprint
from forms import *

insightsBp = Blueprint('insightsBp', __name__)