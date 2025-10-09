from amcat4.system_index.mapping import eMapping, eObject, eObjectArray
from amcat4.system_index.util import SystemIndexSpec, Table

VERSION = 2

settings_mapping = eMapping(
    index_settings=eObject(
        name='keyword',
        description='text',
        contact=eObject(
            name='keyword',
            email='keyword',
            url='keyword',
        ),
        guest_role='keyword',
        archived='date',
        folder='keyword',
        image_url='keyword',
        fields='flattened',
    ),
    server_settings=eObject(
        name='keyword',
        description='text',
        contact=eObject(
            name='keyword',
            email='keyword',
            url='keyword',
        ),
        external_url='keyword',
        welcome_text='text',
        information_links='flattened',
        welcome_buttons='flattened',
        icon='keyword',
    )
)


roles_mapping = eMapping(
    email='keyword',
    index='keyword',
    role='keyword',
)


requests_mapping = eMapping(
    request_type='keyword',
    email='keyword',
    index='keyword',
    status='keyword',
    message='text',
    timestamp='date',
    role='keyword',
    name='text',
    description='text',
    folder='keyword',
)

TABLES = {
    "settings": settings_mapping,

}



SPEC = SystemIndexSpec(
    version=1,
    tables=[
        Table(path='settings', model=SI_Settings, es_mapping=SI_Settings_mapping),
        Table(path='users', model=SI_Users, es_mapping=SI_Users_mapping),
        Table(path='requests', model=SI_Requests, es_mapping=SI_Requests_mapping)
    ]
)
