from amcat4.systemdata.versions import v1, v2

VERSIONS = {1: v1, 2: v2}
LATEST_VERSION = max(VERSIONS.keys())

# INDEX NAMES
settings_index = VERSIONS[LATEST_VERSION].settings_index
roles_index = VERSIONS[LATEST_VERSION].roles_index
requests_index = VERSIONS[LATEST_VERSION].requests_index
fields_index = VERSIONS[LATEST_VERSION].fields_index

# INDEX ID FUNCTIONS
settings_index_id = VERSIONS[LATEST_VERSION].settings_index_id
roles_index_id = VERSIONS[LATEST_VERSION].roles_index_id
requests_index_id = VERSIONS[LATEST_VERSION].requests_index_id
fields_index_id = VERSIONS[LATEST_VERSION].fields_index_id
