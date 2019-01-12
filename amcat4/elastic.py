import hashlib
import json
import logging

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

es = Elasticsearch()

PREFIX = "amcat4_"
DOCTYPE = "article"
SYS_INDEX = "amcat4system"
SYS_MAPPING = "sys"
REQUIRED_FIELDS = ["title", "date", "text"]
HASH_FIELDS = REQUIRED_FIELDS + ["url"]
DEFAULT_QUERY_FIELDS = HASH_FIELDS


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



def _get_hash(document):
    """
    Get the hash for a document
    """
    hash_dict = {key: document.get(key) for key in HASH_FIELDS}
    hash_str = json.dumps(hash_dict, sort_keys=True, ensure_ascii=True).encode('ascii')
    m = hashlib.sha224()
    m.update(hash_str)
    return m.hexdigest()


def _get_es_actions(index, doc_type, documents):
    """
    Create the Elasticsearch bulk actions from article dicts.
    If you provide a list to ID_SEQ_LIST, the hashes are copied there
    """
    for document in documents:
        for f in REQUIRED_FIELDS:
            if f not in document:
                raise ValueError("Field {f} not present in article {article}")
        _id = _get_hash(document)
        yield {
            "_index": index,
            "_type": doc_type,
            "_id": _id,
            **document
        }


def upload_documents(project_name: str, documents):
    """
    Upload documents to this project

    :param project_name: The name of the project (without prefix)
    :param documents: A sequence of article dictionaries
    :return:
    """
    index = "".join([PREFIX, project_name])
    actions = list(_get_es_actions(index, DOCTYPE, documents))
    bulk(es, actions)
    return [action['_id'] for action in actions]


def get_document(project_name: str, id: str):
    """
    Get a single document from this project

    :param project_name: The name of the project (without prefix)
    :param id: The document id (hash)
    :return: the source dict of the document
    """
    index = "".join([PREFIX, project_name])
    return es.get(index, DOCTYPE, id)['_source']


def query_documents(project_name: str, query_string: str = None, **kwargs):
    """
    Conduct a query_string query, returning the found documents

    :param project_name: The name of the project (without prefix)
    :param query_string: The elasticsearch query_string
    :return: an iterator of article dicts
    """
    index = "".join([PREFIX, project_name])
    if query_string:
        body = dict(query=dict(query_string=dict(default_field="text", query=query_string)))
    else:
        body = dict(query=dict(match_all={}))

    result = es.search(index, DOCTYPE, body, **kwargs)
    return [dict(_id=hit['_id'], **hit['_source']) for  hit in result['hits']['hits']]


def flush():
    es.indices.flush()
