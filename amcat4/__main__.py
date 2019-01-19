import logging
import sys

from amcat4 import auth
from amcat4.elastic import setup_elastic, create_project, upload_documents, list_projects
from amcat4.api import app


SOTU_PROJECT = "state_of_the_union"


def upload_test_data():
    import io, csv, urllib.request, sys
    url = "https://raw.githubusercontent.com/ccs-amsterdam/example-text-data/master/sotu.csv"
    url_open = urllib.request.urlopen(url)
    csv.field_size_limit(sys.maxsize)
    csvfile = csv.DictReader(io.TextIOWrapper(url_open, encoding='utf-8'))
    create_project(SOTU_PROJECT)
    docs = [dict(title="{Year}: {President}".format(**row),
                 text=row['Text'],
                 date=row['Date'],
                 president=row['President'],
                 year=row['Year'],
                 party=row['Party'])
            for row in csvfile]
    upload_documents(SOTU_PROJECT, docs)
    return csvfile


if __name__ == '__main__':
    logging.basicConfig(format='[%(levelname)-7s:%(name)-15s] %(message)s', level=logging.INFO)
    setup_elastic()
    es_logger = logging.getLogger('elasticsearch')
    es_logger.setLevel(logging.WARNING)
    if not auth.has_user():
        logging.warning("**** No user detected, creating superuser admin:admin ****")
        auth.create_user("admin", "admin", roles=[auth.ROLE_ADMIN])
    if "--create-test-project" in sys.argv:
        # [WvA] I apologize for the argument parsing
        if SOTU_PROJECT not in list_projects():
            logging.info("**** Creating test project {} ****".format(SOTU_PROJECT))
            upload_test_data()
    app.run(debug=True)
