# - 4 level cache dir structure based on hash of filename
# - make a system index for objectstore that has
#   - context: project_id or _server
#   - filename
#   - path (like s3)
#   - subdir: first 4 chars of hash(path/filename)
#   - size
# - hash determines subfolders: the full path is preserved inside subfolder
# - The system index should be repairable based on the file structure.
#   - first level folder is the project_id or _server
#   - a repair function runs over all files, checks if they are in the index, and adds them if not

# OR should we only use the path as first level and then only subfolders for the filename?
