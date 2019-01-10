import logging

from amcat4 import auth
from amcat4.elastic import setup_elastic
from amcat4.api import app

if __name__ == '__main__':
    logging.basicConfig(format='[%(levelname)-7s:%(name)-15s] %(message)s', level=logging.INFO)
    setup_elastic()
    if not auth.has_user():
        logging.warning("**** No user detected, creating superuser admin:admin ****")
        auth.create_user("admin", "admin", roles=[auth.ROLE_ADMIN], check_email=False)
    app.run(debug=True)
