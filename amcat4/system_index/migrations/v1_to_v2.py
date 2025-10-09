
from pydantic import BaseModel
from typing import Iterable
import elasticsearch.helpers
from amcat4.elastic_connection import _elastic_connection
from amcat4.system_index.util import SINGLE_DOC_INDEX_ID, SystemIndexSpec, Table, create_or_refresh_system_index, get_system_index_name
import json
from amcat4.system_index.specifications import v1, v2


def migrate():
    create_or_refresh_system_index(v2.SPEC)

    for ix in export_v1_index_list():
        if ix.id == "_global":
            import_v2_settings(ix)
            import_v2_requests(ix)
            import_v2_users(ix)
        else:
            import_v2_settings(ix)
            import_v2_users(ix)


def export_v1_index_list() -> Iterable[v1.SI_IndexList]:
    si = get_system_index_name(v1.SPEC.version)
    elastic = _elastic_connection()

    # There used to be an even older version with an older migration method.
    # We don't support migrating from that version anymore.
    global_doc = elastic.get(index=si, id="_global", source_includes='version')
    version = global_doc["_source"].get("version", 0)
    if version != 2:
        raise ValueError(
            "Cannot automatically migrate from current system index, because its a very old version. "
            "So old that we would be surprised if you ever even see this message, but if you do, "
            "and you really need to migrate, please contact us"
        )

    for entry in elasticsearch.helpers.scan(elastic, index=si, _source=True):
        yield v1.SI_IndexList(
            id=entry["_id"],
            **entry["_source"]
        )



def import_v2_index_settings(v1_ix: v1.SI_IndexList):
    si_settings = get_system_index_name(v2.SPEC.version, 'settings')

    d = v1_ix.model_dump(include={
        'id','name','description','guest_role',
        'archived','folder','image_url','contact','fields'})
    doc = v2.SI_Settings.model_validate(**d)

    doc_dict = doc.model_dump()
    id = doc_dict.pop('id')

    _elastic_connection().index(
        index=si_settings,
        id=id,
        document=doc_dict,
    )


def import_v2_server_settings(vi_global: v1.SI_IndexList):
    si_settings = get_system_index_name(v2.SPEC.version, 'settings')

    # V2 does specify the client data
    client_data = json.loads(vi_global.client_data or "{}")
    branding = vi_global.branding.model_dump() if vi_global.branding else {}

    doc = v2.SI_Settings.model_validate(
        id="_global",
        name=vi_global.name,
        description=None,
        server_name=branding.get("server_name"),
        server_url=branding.get('server_url'),
        welcome_text=branding.get('welcome_text'),
        server_icon=branding.get('server_icon'),
        welcome_buttons=client_data.get("welcome_buttons"),
        information_links=client_data.get("information_links"),
        contact=vi_global.contact,
    )

    doc_dict = doc.model_dump()
    id = doc_dict.pop('id')
    _elastic_connection().index(
        index=si_server_settings,
        id=id,
        document=doc_dict,
    )


def import_v2_users(v1_ix: v1.SI_IndexList):
    si_users = get_system_index_name(v2.SPEC.version, 'users')

    actions = []
    for role in v1_ix.roles:
        doc = v2.SI_Users(
            email=role.email,
            index=v1_ix.id,
            role=role.role
        )
        actions.append({
            "_index": si_users,
            "_id": f"{doc.email}_{doc.index}",
            "_source": doc.model_dump()
        })

    if len(actions) > 0:
        elasticsearch.helpers.bulk(_elastic_connection(), actions)



def import_v2_requests(v1_global: v1.SI_IndexList):
    si_requests = get_system_index_name(v2.SPEC.version, 'requests')

    actions = []
    for r in v1_global.requests or []:
        type = r.get("request_type")
        if type == 'role':
            doc = v2.SI_RoleRequest(**r)
        else:
            doc = v2.SI_CreateProjectRequest(**r)

        actions.append({
            "_index": si_requests,
            "_id": f"{doc.request_type}_{doc.email}_{doc.index or '_global'}",
            "_source": doc.model_dump()
        })

    if len(actions) > 0:
        elasticsearch.helpers.bulk(_elastic_connection(), actions)
