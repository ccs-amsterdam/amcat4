from amcat4.systemdata.versions import v1, v2

VERSIONS = {1: v1, 2: v2}
LATEST_VERSION = max(VERSIONS.keys())

# INDEX NAME FUNTIONS: settings_index_name(), roles_index_name(), etc
settings_index_name = VERSIONS[LATEST_VERSION].settings_index_name
roles_index_name = VERSIONS[LATEST_VERSION].roles_index_name
requests_index_name = VERSIONS[LATEST_VERSION].requests_index_name
apikeys_index_name = VERSIONS[LATEST_VERSION].apikeys_index_name
fields_index_name = VERSIONS[LATEST_VERSION].fields_index_name
objectstorage_index_name = VERSIONS[LATEST_VERSION].objectstorage_index_name

# INDEX ID FUNCTIONS: roles_index_id(email, role_context), etc
settings_index_id = VERSIONS[LATEST_VERSION].settings_index_id
roles_index_id = VERSIONS[LATEST_VERSION].roles_index_id
requests_index_id = VERSIONS[LATEST_VERSION].requests_index_id
apikeys_index_id = VERSIONS[LATEST_VERSION].apikeys_index_id
fields_index_id = VERSIONS[LATEST_VERSION].fields_index_id
objectstorage_index_id = VERSIONS[LATEST_VERSION].objectstorage_index_id
