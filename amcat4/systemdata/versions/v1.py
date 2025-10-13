from amcat4.elastic_mapping import nested_field, object_field, ElasticMapping
from amcat4.systemdata.util import SystemIndexMapping

VERSION = 1

mapping: ElasticMapping = dict(
    archived={"type": "text"},
    client_data={"type": "text"},
    description={"type": "text"},
    external_url={"type": "keyword"},
    folder={"type": "keyword"},
    guest_role={"type": "keyword"},
    image_url={"type": "keyword"},
    name={"type": "text"},
    version={"type": "integer"},
    branding=object_field(
        server_name={"type": "text"},
        server_icon={"type": "keyword"},
        server_url={"type": "keyword"},
        welcome_text={"type": "text"},
    ),
    contact=object_field(
        name={"type": "keyword"},
        email={"type": "keyword"},
        url={"type": "keyword"},
    ),
    fields=nested_field(
        field={"type": "text"},
        settings=object_field(
            identifier={"type": "boolean"},
            type={"type": "text"},
            elastic_type={"type": "text"},
            client_settings=object_field(
                inDocument={"type": "boolean"},
                inList={"type": "boolean"},
                inListSummary={"type": "boolean"},
                isHeading={"type": "boolean"},
            ),
            metareader=object_field(
                access={"type": "text"},
                max_snippet=object_field(
                    match_chars={"type": "integer"},
                    max_matches={"type": "integer"},
                    nomatch_chars={"type": "integer"},
                ),
            ),
        ),
    ),
    requests=nested_field(
        description={"type": "text"},
        email={"type": "keyword"},
        index={"type": "keyword"},
        message={"type": "text"},
        name={"type": "text"},
        reject={"type": "boolean"},
        role={"type": "keyword"},
        timestamp={"type": "date"},
    ),
    roles=nested_field(
        email={"type": "keyword"},
        role={"type": "keyword"},
    ),
)

SYSTEM_INDICES = [SystemIndexMapping(name="", mapping=mapping)]
