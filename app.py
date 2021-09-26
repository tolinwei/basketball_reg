from flask import Flask, render_template, redirect, url_for, request
import pendulum
from flask import g
import sqlite3
from logging.config import dictConfig

# Basic logging config
# https://flask.palletsprojects.com/en/2.0.x/logging/
dictConfig({
    'version': 1,
    'formatters': {'default': {
        'format': '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
    }},
    'handlers': {'wsgi': {
        'class': 'logging.StreamHandler',
        'stream': 'ext://flask.logging.wsgi_errors_stream',
        'formatter': 'default'
    }},
    'root': {
        'level': 'INFO',
        'handlers': ['wsgi']
    }
})

app = Flask(__name__)

DATABASE = 'basketball_reg.sqlite'


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
    current_date_select = cursor.execute('select * from date where date = "' + current_date + '"')

    if len(current_date_select.fetchall()) == 0:
        app.logger.info('New date, inserting')
        new_date_insert = cursor.execute('insert into date (date) values ("' + current_date + '")')
        conn.commit()
    else:
        app.logger.info('Date already exists')

    # Address
    address_select = cursor.execute('select name, map_link from address')
    address = address_select.fetchall()

    # Select all registered players from another table
    # "registration"
    registered_users_select = cursor.execute(
        'select registration.user_id, name from registration '
        + 'inner join user on registration.user_id = user.id '
        + 'inner join date on registration.date_id = date.id '
        + 'where date.date = "' + current_date + '"'
    )
    # The fetchall() is a list of tuple
    registered_users = registered_users_select.fetchall()

    app.logger.info('registered_users: ' + str(registered_users))

    # Bottom part of the page, list all users, minus the
    # registered ones this week.
    all_users_select = cursor.execute('select id, name from user')
    all_users = all_users_select.fetchall()

    unregistered_users = [user for user in all_users if user not in registered_users]
    app.logger.info('unregistered_users: ' + str(unregistered_users))

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
    app.logger.info('date_id: ' + str(date_id))
    app.logger.info('user_id: ' + str(user_id))
    registration_insert = cursor.execute(
        'insert into registration (date_id, user_id) values (' + str(date_id) + ' , ' + user_id + ')'
    )
    conn.commit()

    return redirect(url_for('index'))


@app.route("/unregister/<user_id>")
def unregister(user_id):
    current_date = get_current_date()

    # DB preparation
    conn = get_conn()
    cursor = conn.cursor()

    current_date_select = cursor.execute('select id from date where date = "' + current_date + '"')
    date_id = current_date_select.fetchall()[0][0]
    app.logger.info('date_id: ' + str(date_id))
    app.logger.info('user_id: ' + str(user_id))
    registration_delete = cursor.execute(
        'delete from registration where date_id = ' + str(date_id) + ' and user_id = ' + user_id
    )
    conn.commit()

    return redirect(url_for('index'))


@app.route("/add_user", methods=['POST'])
def add_user():
    name = request.form['name']
    # Invalid input
    if name == '' or name is None:
        return redirect(url_for('index'))


    # DB preparation
    conn = get_conn()
    cursor = conn.cursor()

    new_user_insert = cursor.execute('insert into user (name) values ("' + name + '")')
    conn.commit()
    return redirect(url_for('index'))


@app.route("/delete/<user_id>")
def delete(user_id):
    current_date = get_current_date()

    # DB preparation
    conn = get_conn()
    cursor = conn.cursor()

    current_date_select = cursor.execute('select id from date where date = "' + current_date + '"')
    date_id = current_date_select.fetchall()[0][0]
    registration_delete = cursor.execute(
        'delete from registration where date_id = ' + str(date_id) + ' and user_id = ' + user_id
    )
    conn.commit()
    user_delete = cursor.execute('delete from user where id = ' + user_id)
    conn.commit()

    return redirect(url_for('admin'))


@app.route("/change_address", methods=['POST'])
def change_address():
    #TODO

    # DB preparation
    conn = get_conn()
    cursor = conn.cursor()

    name = request.form['name']
    map_link = request.form['map_link']
    change_address_update = cursor.execute('update address set name = "' + name + '", map_link = "' + map_link + '" where id = 1 ')
    conn.commit()

    return redirect(url_for('admin'))


# https://flask.palletsprojects.com/en/2.0.x/patterns/sqlite3/
def get_conn():
    conn = getattr(g, '_database', None)
    if conn is None:
        conn = g._database = sqlite3.connect(DATABASE)
    app.logger.info('Opened database successfully')
    return conn


@app.teardown_appcontext
def close_conn(exception):
    conn = getattr(g, '_database', None)
    if conn is not None:
        conn.close()


def get_current_date():
    current_date = pendulum.yesterday().next(pendulum.SATURDAY).strftime('%Y-%m-%d')
    app.logger.info("Current date: " + current_date)
    return current_date