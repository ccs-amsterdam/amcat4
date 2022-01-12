"""
Encapsulates elasticsearch indices  and provides authorisation through user roles

Authorisation rules:
- There are 5 increasing levels of authorisation: None, metareader, reader, writer, admin
- Users can have a global role and a role on any index. Every index can also have a guest role
- Global roles:
  - Writers can create new projects and users (with at most their own global role)
  - Admins can delete projects and assign themselves a role on any index role
- Index roles:
  - None means an index cannot be viewed or accessed in any way (the index is invisible to the user)
  - Metareader means the user can read all properties, do queries, etc., but cannot read the 'text' attribute
    (this is mostly intended to provide access to metadata fields of copyrighted material)
  - Reader can read all properties, do queries, etc., but cannot make changes
  - Writers can add/delete documents, add/delete users (up to their own level), and make other changes (but not delete)
  - Admins can do whatever they want, including deleting the index
- If a user does not have an explicit role on an index, the guest role (if any) is used
- An unauthorized user can still get guest roles, so it can see any indices with a guest role

Note that these rules are not enforced in this module, they should be enforced by the API!
"""


from peewee import Model, CharField, IntegerField, ForeignKeyField

from amcat4 import elastic
from amcat4.auth import Role, User
from amcat4.db import db


class Index(Model):
    name = CharField(unique=True)
    guest_role = IntegerField(null=True)

    class Meta:
        database = db

    def delete_index(self, delete_from_elastic=True):
        """
        Delete this index
        :param delete_from_elastic: if True (default), also delete the underlying elastic table
        """
        self.delete_instance()
        if delete_from_elastic:
            elastic._delete_index(self.name)

    def has_role(self, user: User, role: Role) -> bool:
        """
        Checks whether the given User has at least the required Role
        """
        ir = IndexRole.get_or_none(IndexRole.user == user, IndexRole.index == self)
        actual_role = self.guest_role if ir is None else ir.role
        if not actual_role:
            return False
        else:
            return actual_role and actual_role >= role

    def set_role(self, user: User, role: Role) -> None:
        """
        Sets the role for the given new or existing user; set role to None to remove user from this index.
        This will create/update/delete the role as needed
        """
        ir = IndexRole.get_or_none(IndexRole.user == user, IndexRole.index == self)
        if ir:
            if role is None:
                ir.delete_instance()
            elif role != ir.role:
                ir.role = role
                ir.save()
        elif role is not None:
            IndexRole.create(user=user, index=self, role=role)


class IndexRole(Model):
    user = ForeignKeyField(User, on_delete="CASCADE")
    index = ForeignKeyField(Index, on_delete="CASCADE")
    role = IntegerField()

    class Meta:
        database = db
        indexes = (
            (('user', 'index'), True),  # unique constraint user & index
        )


def create_index(name: str, guest_role: Role = None, create_in_elastic=True, admin: User = None) -> Index:
    """
    Create a new index in both elastic and amcat4
    :param name: Name of the new index (in elastic and amcat4)
    :param guest_role: Guest role for this index, i.e. a user's role if no explicit role is assigned.
    :param admin: if given, add this User as admin
    :param create_in_elastic: if True (default), also create a new elastic index
    """
    if Index.select().where(Index.name == name).exists():
        raise ValueError("Index {name} is already registered".format(**locals()))
    if create_in_elastic:
        if elastic.index_exists(name):
            raise ValueError("Index {name} already exists in elastic".format(**locals()))
        elastic._create_index(name)
    elif not elastic.index_exists(name):
        raise ValueError("Index {name} does not exist in elastic".format(**locals()))

    index = Index.create(name=name, guest_role=guest_role)
    if admin:
        IndexRole.create(user=admin, index=index, role=Role.ADMIN)

    indices = [i.name for i in Index.select()]

    return index
