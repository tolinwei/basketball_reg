from flask import Flask, render_template, redirect, url_for, request
from flask_limiter import Limiter
from flask_limiter.util import get_ipaddr
import pendulum
from flask import g
import sqlite3
import logging

DATABASE = 'basketball_reg.sqlite'

app = Flask(__name__)
limiter = Limiter(
    app,
    key_func=get_ipaddr
)
logger = logging.getLogger()


@app.route("/")
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
    # logger.info('registered_users: ' + str(registered_users))

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
        address=address[0],
        registered_users=registered_users,
        unregistered_users=unregistered_users,
        is_admin=is_admin
    )


@app.route("/admin")
def admin():
    return index(True)


@app.route("/register/<user_id>")
@limiter.limit('2/hour;5/day')
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

