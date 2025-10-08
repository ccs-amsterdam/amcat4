# Specifications of system indices.
#
# A specification defines the pydantic models and elasticsearch mappings for a version.
# The specification is used in two places:
# - in system_index.py to create the
# - in migrations/*.py to manage the migrations safely
#
# NOTE ABOUT IMPORTED MODELS:
# A system index specification can import models from amcat4.models.py. When you create a
# new version, you should store a copy of the models used in the old version in v[old]_models.py (see v1_models.py)
# and change the import in v[old].py to import from v[old]_models.py.
# For the current version we do import directly from amcat4.models.py, because these need to be in sync.
