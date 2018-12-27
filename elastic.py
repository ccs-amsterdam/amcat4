import logging

from elasticsearch import Elasticsearch

es = Elasticsearch()

PREFIX = "amcat4_"
SYS_INDEX = "amcat4system"
SYS_MAPPING = "sys"

def setup_elastic(*hosts):
    """
    Check whether we can connect with elastic
    """
    global es
    logging.debug("Connecting with elasticsearch at {}".format(hosts or "(default: localhost:9200)"))
    es = Elasticsearch(hosts or None)
    if not es.ping():
        raise Exception("Cannot connect to elasticsearch server [{}]".format(hosts))
    if not es.indices.exists(SYS_INDEX):
        logging.info("Creating amcat4 system index: {}".format(SYS_INDEX))
        es.indices.create(SYS_INDEX)


def list_projects() -> [str]:
    """
    List all projects (i.e. indices starting with PREFIX) on the connected elastic cluster
    """
    result = es.indices.get(PREFIX + "*")
    names = [x[len(PREFIX):] for x in result.keys()]
    return names


def create_project(name: str):
    """
    Create a new project

    :param name: The name of the new index (without prefix)
    """
    name = "".join([PREFIX, name])
    es.indices.create(name)


def delete_project(name: str, ignore_missing=False):
    """
    Create a new project

    :param name: The name of the new index (without prefix)
    :param ignore_missing: If True, do not throw exception if index does not exist
    """
    name = "".join([PREFIX, name])
    es.indices.delete(name, ignore=([404] if ignore_missing else []))
