from peewee import SqliteDatabase

from .config import settings

db = SqliteDatabase(settings.amcat4_db_name, pragmas={'foreign_keys': 1})


def initialize_if_needed():
    from amcat4.auth import User
    from amcat4.index import Index, IndexRole
    db.create_tables([User, Index, IndexRole])
