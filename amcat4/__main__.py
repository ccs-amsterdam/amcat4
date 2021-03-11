"""
AmCAT4 REST API
"""

import logging
import sys
import io
import csv
import urllib.request

from amcat4 import auth
from amcat4.auth import Role, User
from amcat4.db import initialize_if_needed
from amcat4.elastic import setup_elastic, upload_documents
from amcat4.api import app
from amcat4.index import create_index, Index

SOTU_INDEX = "state_of_the_union"


def upload_test_data() -> Index:
    url = "https://raw.githubusercontent.com/ccs-amsterdam/example-text-data/master/sotu.csv"
    url_open = urllib.request.urlopen(url)
    csv.field_size_limit(sys.maxsize)
    csvfile = csv.DictReader(io.TextIOWrapper(url_open, encoding='utf-8'))

    index = create_index(SOTU_INDEX)

    docs = [dict(title="{Year}: {President}".format(**row),
                 text=row['Text'],
                 date=row['Date'],
                 president=row['President'],
                 year=row['Year'],
                 party=row['Party'])
            for row in csvfile]
    columns = {"president": "keyword", "party": "keyword", "year": "int"}
    upload_documents(SOTU_INDEX, docs, columns)
    return index


import argparse
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--create-test-index', action='store_true')
args = parser.parse_args()

logging.basicConfig(format='[%(levelname)-7s:%(name)-15s] %(message)s', level=logging.INFO)
setup_elastic()
initialize_if_needed()
es_logger = logging.getLogger('elasticsearch')
es_logger.setLevel(logging.WARNING)
if not User.select().where(User.email == "admin").exists():
    logging.warning("**** No user detected, creating superuser admin:admin ****")
    auth.create_user("admin", "admin", Role.ADMIN)
if args.create_test_index:
    if not Index.select().where(Index.name == SOTU_INDEX):
        logging.info("**** Creating test index {} ****".format(SOTU_INDEX))
        admin = User.get(User.email == "admin")
        upload_test_data().set_role(admin, Role.ADMIN)
app.run(debug=True)
