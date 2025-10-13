from elasticsearch import NotFoundError
from amcat4.systemdata.roles import elastic_create_or_update_role
from amcat4.systemdata.versions.v2 import SETTINGS_INDEX, settings_index_id
from amcat4.elastic import es
from amcat4.models import IndexSettings
from amcat4.systemdata.settings import create_index_settings, delete_index_settings, update_index_settings


def create_index(new_index: IndexSettings, admin_email: str | None = None):
    """
    An index needs to exist in two places: as an elasticsearch index, and as a document in the settings index.
    This function creates the elasticsearch index first, and then creates the settings document.
    """
    index_id = settings_index_id(new_index.id)
    if es().exists(index=SETTINGS_INDEX, id=index_id):
        raise ValueError(f'Index "{id}" already exists')

    es().indices.create(index=new_index.id, mappings={"dynamic": "strict", "properties": {}})
    create_index_settings(new_index, admin_email)


def update_index(update_index: IndexSettings):
    """
    Update index settings
    """
    update_index_settings(update_index)


def delete_index(index_id: str, ignore_missing: bool = False):
    """
    Delete both the index and the index settings
    """
    _es = es().options(ignore_status=404) if ignore_missing else es()
    _es.indices.delete(index=index_id)
    delete_index_settings(index_id, ignore_missing)
