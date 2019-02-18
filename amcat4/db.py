import logging

from peewee import *
import sys

# IF we're running nose tests, we want an in-memory db
if 'nose' in sys.modules.keys():
    logging.warning("I think you're unit testing: using in-memory db")
    db = SqliteDatabase(':memory:')
else:
    db = SqliteDatabase('amcat4.db')


def initialize_if_needed():
    from amcat4.auth import User
    db.create_tables([User])
