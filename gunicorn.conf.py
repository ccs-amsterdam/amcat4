# CURRENTLY USING UVICORN INSTEAD OF UNICORN BECAUSE IT SEEMS TO MESS UP PEEWEE (which we'll replace with SQLAlchemy)
# use in gunicorn as: env/bin/gunicorn amcat4.api:app --c gunicorn.conf.py

# Workers
workers = 5
worker_class = 'uvicorn.workers.UvicornWorker'

# Socket
bind = 'localhost:5001'

# Logging
# loglevel = 'debug'
# accesslog = '/tmp/amcat4annotator_access_log'
# errorlog =  '/tmp/amcat4annotator_error_log'
