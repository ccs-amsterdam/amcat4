from amcat4.elastic.util import BulkInsertAction, es_bulk_create
from amcat4.models import ObjectStorage

## Should we even do this?
# Should we not just use s3 directly, and use redis to cache metadata if needed?
# So on presigned post compute total size
# Keep total size in redis
# Create pending_size/index/field/filename for pending files
# As long as presigned posts are valid, include pending size in total
# Presigned get just reads head from s3 and redirects to etagged version
# with immutable cache.
#
# Before redis, just don't cache total size computation for quick implementation
#
# The main downside is that it's not easy to check which elastic documents have multimedia objects.


def register_objects(objects: list[ObjectStorage], overwrite: bool = False):
    def generator():
        for obj in objects:
            yield BulkInsertAction(
                index="amcat_multimedia", id=f"{obj.index}:{obj.field}:{obj.filename}", doc=obj.model_dump()
            )

    es_bulk_create(generator(), overwrite=overwrite)
