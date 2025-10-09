from amcat4.systemindices.mapping import SI_ElasticMapping, SI_NestedField

branding_mapping: SI_NestedField = {
    "type": "object",
    "dynamic": "strict",
    "properties": dict(
        server_name={"type": "text"},
        server_icon={"type": "keyword"},
        server_url={"type": "keyword"},
        welcome_text={"type": "text"},
    ),
}

contact_mapping: SI_NestedField = {
    "type": "object",
    "dynamic": "strict",
    "properties": dict(
        name={"type": "keyword"},
        email={"type": "keyword"},
        url={"type": "keyword"},
    ),
}

fields_mapping: SI_NestedField = {
    "type": "nested",
    "dynamic": "strict",
    "properties": dict(
        field={"type": "text"},
        settings={
            "type": "object",
            "dynamic": "strict",
            "properties": dict(
                identifier={"type": "boolean"},
                type={"type": "text"},
                elastic_type={"type": "text"},
                client_settings={
                    "type": "object",
                    "dynamic": "strict",
                    "properties": dict(
                        inDocument={"type": "boolean"},
                        inList={"type": "boolean"},
                        inListSummary={"type": "boolean"},
                        isHeading={"type": "boolean"},
                    ),
                },
                metareader={
                    "type": "object",
                    "dynamic": "strict",
                    "properties": dict(
                        access={"type": "text"},
                        max_snippet={
                            "type": "object",
                            "dynamic": "strict",
                            "properties": dict(
                                match_chars={"type": "integer"},
                                max_matches={"type": "integer"},
                                nomatch_chars={"type": "integer"},
                            ),
                        },
                    ),
                },
            ),
        },
    ),
}

mapping: SI_ElasticMapping = dict(
    archived={"type": "text"},
    branding=branding_mapping,
    client_data={"type": "text"},
    contact=contact_mapping,
    description={"type": "text"},
    external_url={"type": "keyword"},
    fields=fields_mapping,
    folder={"type": "keyword"},
    guest_role={"type": "keyword"},
    image_url={"type": "keyword"},
    name={"type": "text"},
    requests={
        "type": "nested",
        "dynamic": "strict",
        "properties": dict(
            description={"type": "text"},
            email={"type": "keyword"},
            index={"type": "keyword"},
            message={"type": "text"},
            name={"type": "text"},
            reject={"type": "boolean"},
            role={"type": "keyword"},
            timestamp={"type": "date"},
        ),
    },
    roles={
        "type": "nested",
        "dynamic": "strict",
        "properties": dict(
            email={"type": "keyword"},
            role={"type": "keyword"},
        ),
    },
    version={"type": "integer"},
)
