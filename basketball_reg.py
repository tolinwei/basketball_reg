import json
import logging
import pprint
import sqlite3
import time

import pendulum
import requests
from flask import Flask, render_template, redirect, url_for, request
from flask import g
from flask_limiter import Limiter
from flask_limiter.util import get_ipaddr
from flask_login import LoginManager, login_required, login_user, UserMixin, logout_user

# Logging statement for local dev environment, will break in Pythonanywhere
# from logging.config import dictConfig
#
# dictConfig({
#     'version': 1,
#     'formatters': {'default': {
#         'format': '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
#     }},
#     'handlers': {'wsgi': {
#         'class': 'logging.StreamHandler',
#         'stream': 'ext://flask.logging.wsgi_errors_stream',
#         'formatter': 'default'
#     }},
#     'root': {
#         'level': 'INFO',
#         'handlers': ['wsgi']
#     }
# })

DATABASE = 'basketball_reg.sqlite'
PASSWORD = '<PASSWORD>'
WEATHER_LOC_LAT = 42.3622133
WEATHER_LOC_LONG = -71.1175175
WEATHER_API_KEY = '<WEATHER_API_KEY>'

app = Flask(__name__)
logger = logging.getLogger()

# Flask-Limiter
limiter = Limiter(
    app,
    key_func=get_ipaddr
)

# Flask-Login
# python -c 'import os; print(os.urandom(16))'
app.config['SECRET_KEY'] = b'"C(C\xf4$\nK \x97\xfa\xc2t\x0c\xc6\x85'
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)


@app.route('/')
@login_required
def index(is_admin=False):
    # Fetch next Saturday, based on current timestamp
    # Cutoff is Saturday 12AM ET (or the timezone of the server?)
    current_date = get_current_date()

    # DB preparation
    conn = get_conn()
    cursor = conn.cursor()

    # Check if there's such record in SQLite3, if not insert
    # into "week" table (id, date, note)
    try:
        current_date_select = cursor.execute('select * from date where date = "' + current_date + '"')
    except sqlite3.Error as err:
        logger.error(err)
        return render_template('error.html', error_message=err)

    if len(current_date_select.fetchall()) == 0:
        logger.info('New date, inserting')
        try:
            new_date_insert = cursor.execute('insert into date (date) values ("' + current_date + '")')
            conn.commit()
        except sqlite3.Error as err:
            logger.error(err)
            return render_template('error.html', error_message=err)
    else:
        logger.info('Date already exists')

    # Weather
    weather_response = requests.get(
        'https://api.openweathermap.org/data/2.5/onecall'
        + '?lat=' + str(WEATHER_LOC_LAT)
        + '&lon=' + str(WEATHER_LOC_LONG)
        + '&exclude=current,minutely,hourly,alerts'
        + '&units=metric&lang=zh_cn'
        + '&appid=' + WEATHER_API_KEY
    )
    weather_response_dict = json.loads(weather_response.text)

    pp = pprint.PrettyPrinter(indent=4)
    pp.pprint(weather_response_dict)

    if 'daily' in weather_response_dict:
        for day_forecast in weather_response_dict['daily']:
            if time.strftime('%Y-%m-%d', time.localtime(day_forecast['dt'])) == current_date:
                day_temp = day_forecast['temp']['day']
                weather_description = day_forecast['weather'][0]['description']
                app.logger.info(day_temp)
                app.logger.info(weather_description)
    else:
        day_temp = 0
        weather_description = 'Error'

    # Address
    try:
        address_select = cursor.execute('select name, map_link from address')
        address = address_select.fetchall()
    except sqlite3.Error as err:
        logger.error(err)
        return render_template('error.html', error_message=err)

    # Select all registered players from another table
    # "registration"
    try:
        registered_users_select = cursor.execute(
            'select registration.user_id, name from registration '
            + 'inner join user on registration.user_id = user.id '
            + 'inner join date on registration.date_id = date.id '
            + 'where date.date = "' + current_date + '"'
        )
    except sqlite3.Error as err:
        logger.error(err)
        return render_template('error.html', error_message=err)
    # The fetchall() is a list of tuple
    registered_users = registered_users_select.fetchall()
    logger.info('registered_users: ' + str(registered_users))

    # Bottom part of the page, list all users, minus the
    # registered ones this week.
    try:
        all_users_select = cursor.execute('select id, name from user')
        all_users = all_users_select.fetchall()
    except sqlite3.Error as err:
        logger.error(err)
        return render_template('error.html', error_message=err)

    unregistered_users = [user for user in all_users if user not in registered_users]
    logger.info('unregistered_users: ' + str(unregistered_users))

    return render_template(
        'index.html',
        current_date=current_date,
        day_temp=day_temp,
        weather_description=weather_description,
        address=address[0],
        registered_users=registered_users,
        unregistered_users=unregistered_users,
        is_admin=is_admin
    )


@app.route("/admin")
@login_required
def admin():
    return index(True)


@app.route("/register/<user_id>")
@limiter.limit('2/hour;5/day')
@login_required
def register(user_id):
    # This URL cannot be access directly
    # otherwise the date may not have been created (edge case though)
    # AKA assuming the date has been inserted
    current_date = get_current_date()

    # DB preparation
    conn = get_conn()
    cursor = conn.cursor()

    current_date_select = cursor.execute('select id from date where date = "' + current_date + '"')
    date_id = current_date_select.fetchall()[0][0]

    # Prevent double register, check at first
    try:
        registration_check_select = cursor.execute(
            'select * from registration where date_id = "' + str(date_id) + '" and user_id = "' + user_id + '"'
        )
    except sqlite3.Error as err:
        logger.error(err)
        return render_template('error.html', error_message=err)
    if len(registration_check_select.fetchall()) != 0:
        return redirect(url_for('index'))

    # Actual registration
    try:
        registration_insert = cursor.execute(
            'insert into registration (date_id, user_id) values (' + str(date_id) + ' , ' + user_id + ')'
        )
        conn.commit()
    except sqlite3.Error as err:
        logger.error(err)
        return render_template('error.html', error_message=err)

    return redirect(url_for('index'))


@app.route("/deregister/<user_id>")
@limiter.limit('2/hour;5/day')
@login_required
def deregister(user_id):
    current_date = get_current_date()

    # DB preparation
    conn = get_conn()
    cursor = conn.cursor()

    try:
        current_date_select = cursor.execute('select id from date where date = "' + current_date + '"')
    except sqlite3.Error as err:
        logger.error(err)
        return render_template('error.html', error_message=err)
    date_id = current_date_select.fetchall()[0][0]
    try:
        registration_delete = cursor.execute(
            'delete from registration where date_id = ' + str(date_id) + ' and user_id = ' + user_id
        )
        conn.commit()
    except sqlite3.Error as err:
        logger.error(err)
        return render_template('error.html', error_message=err)

    return redirect(url_for('index'))


@app.route("/add_user", methods=['POST'])
@limiter.limit('2/day')
@login_required
def add_user():
    name = request.form['name']
    # Invalid input
    if name == '' or name is None:
        return redirect(url_for('index'))

    # DB preparation
    conn = get_conn()
    cursor = conn.cursor()

    try:
        new_user_insert = cursor.execute('insert into user (name) values ("' + name + '")')
        conn.commit()
    except sqlite3.Error as err:
        logger.error(err)
        return render_template('error.html', error_message=err)
    return redirect(url_for('index'))


@app.route("/delete/<user_id>")
@limiter.limit('2/day')
@login_required
def delete(user_id):
    current_date = get_current_date()

    # DB preparation
    conn = get_conn()
    cursor = conn.cursor()

    current_date_select = cursor.execute('select id from date where date = "' + current_date + '"')
    date_id = current_date_select.fetchall()[0][0]
    try:
        registration_delete = cursor.execute(
            'delete from registration where date_id = ' + str(date_id) + ' and user_id = ' + user_id
        )
        conn.commit()
        user_delete = cursor.execute('delete from user where id = ' + user_id)
        conn.commit()
    except sqlite3.Error as err:
        logger.error(err)
        return render_template('error.html', error_message=err)

    return redirect(url_for('admin'))


@app.route("/change_address", methods=['POST'])
@limiter.limit('2 per day')
@login_required
def change_address():
    # DB preparation
    conn = get_conn()
    cursor = conn.cursor()

    name = request.form['name']
    map_link = request.form['map_link']

    # Invalid input handling
    if len(name) == 0 or len(name) > 64 or len(map_link) == 0:
        return 'Both fields cannot be empty and name needs to be shorter than 64'
    try:
        change_address_update = cursor.execute('update address set name = "' + name + '", map_link = "' + map_link + '" where id = 1 ')
        conn.commit()
    except sqlite3.Error as err:
        logger.error(err)
        return render_template('error.html', error_message=err)

    return redirect(url_for('admin'))


@app.route('/test_error')
def test_error():
    current_date = get_current_date()

    # DB preparation
    conn = get_conn()
    cursor = conn.cursor()
    try:
        current_date_select = cursor.execute('select id from fake_table where date = "' + current_date + '"')
    except sqlite3.Error as err:
        logger.error(err)
        return render_template('error.html', error_message=err)

    return render_template(
        'error.html',
        error_message='Primar lorem ipsum dolor sit amet, consectetur adipiscing elit lorem ipsum dolor.')


@app.route('/test_limiter')
@limiter.limit('2 per hour')
def test_limiter():
    return render_template(
        'error.html',
        error_message='Primar lorem ipsum dolor sit amet, consectetur adipiscing elit lorem ipsum dolor.')


@app.route('/test_login')
def test_login():
    return render_template('login.html')


# https://flask.palletsprojects.com/en/2.0.x/patterns/sqlite3/
def get_conn():
    conn = getattr(g, '_database', None)
    if conn is None:
        conn = g._database = sqlite3.connect(DATABASE)
    logger.info('Opened database successfully')
    return conn


@app.teardown_appcontext
def close_conn(exception):
    conn = getattr(g, '_database', None)
    if conn is not None:
        conn.close()


def get_current_date():
    current_date = pendulum.yesterday('America/New_York').next(pendulum.SATURDAY).strftime('%Y-%m-%d')
    return current_date


# User login and persistence
class User(UserMixin):
    def __init__(self, id):
        self.id = id  # required by Flask-Login, has to be named as `id`


@app.route('/login', methods=['POST', 'GET'])
def login():
    if request.method == 'GET':
        return render_template('login.html')
    else:  # login authentication
        password = request.form['password']
        if password == PASSWORD:
            user = User(1)
            login_user(user)
            # Safety check (skip)
            # next = flask.request.args.get('next')
            return redirect(url_for('index'))
        else:
            logger.info('Wrong password')
            return render_template(
                'error.html',
                error_message='密码错误'
            )


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# Flask-Login
# callback to reload the user object
@login_manager.user_loader
def load_user(user_id):
    return User(user_id)


