
# basketball_reg

A light-weight and mobile-first app that helps to gather the intention to play basketball on weekends.

Features:
1. One-click on names to register/unregister.
2. Automatic refresh the date (every Saturday). The cutoff time is Saturday midnight ET.
3. Persistent user information. Only needs to add once, and the users will be carried over to next week.

### Open source framework used:
- Flask - Python web development framework: https://flask.palletsprojects.com/en/2.0.x/
- Bulma - CSS framework: https://bulma.io

### Project structure
```
|- basketball_reg.py (Main entrance that drives all the logic)
|- templates (folder for all the front-end templates)
        |- index.html (Main front-end page)
        |- error.html (Error page)
|- db_schema.sql (SQLite3 schema file to recover/rebuild the database)
```

### Deployment
- Pythonanywhere (free): http://pythonanywhere.com
- Ubuntu: https://www.linode.com/docs/guides/flask-and-gunicorn-on-ubuntu/
