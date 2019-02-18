import logging

from amcat4 import db


def setup_package():
    logging.warning("Setting up!")
    db.initialize_if_needed()
