import os

from peewee import SqliteDatabase

db_name = os.environ.get("AMCAT4_DB_NAME", "amcat4.db")
db = SqliteDatabase(db_name, pragmas={'foreign_keys': 1})


def initialize_if_needed():
    from amcat4.auth import User
    from amcat4.index import Index, IndexRole
    db.create_tables([User, Index, IndexRole])
