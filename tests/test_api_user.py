import urllib
from collections import namedtuple

from amcat4.auth import verify_token, create_user, User, verify_user, Role
from nose.tools import assert_equal, assert_is_not_none

from tests.tools import QueryTestCase, ApiTestCase


class TestQuery(ApiTestCase):
    def test_get_token(self):
        self.get('/auth/token/', user=None, check=401, check_error="Getting a token should require authorization")
        r = self.get('/auth/token/')
        token = r.json['token']
        assert_equal(verify_token(token), self.user)
        self.get('/index/', user=None, check=401)
        assert_equal(self.get('/index/', headers={"Authorization": "Bearer {}".format(token)}).status_code, 200)

    def getuser(self, user, as_user=None, **args):
        if not isinstance(user, str):
            user = user.email
        return self.get("/users/" + user, user=as_user, **args).json

    def test_get_user(self):
        """Test GET user functionality and authorization"""
        self.getuser("unknown user", as_user=None, check=401)
        self.getuser(self.user, as_user=None, check=401)

        # user can only see its own info:
        assert_equal(self.getuser(self.user, as_user=self.user), {"email": self.user.email, "global_role": None})
        self.getuser(self.admin, as_user=self.user, check=401)
        # admin can see everyone
        assert_equal(self.getuser(self.admin, as_user=self.admin), {"email": self.admin.email, "global_role": 'ADMIN'})
        assert_equal(self.getuser(self.user, as_user=self.admin), {"email": self.user.email, "global_role": None})

    def test_create_user(self):
        self.post('/users/', check=401, check_error="Creating user should require auth")
        _user = namedtuple("_user", "email pwd")
        u = _user(email='testuser@example.com', pwd='test')
        self.post("/users/", check=401, check_error="creating user requires >=WRITER")
        self.getuser(u, as_user=self.admin, check=404)
        self.post("/users/", user=self.writer, json=dict(email=u.email, password=u.pwd))
        assert_equal(self.getuser(u, as_user=u, password=u.pwd), {"email": u.email, "global_role": None})
        self.post("/users/", user=self.writer, json=dict(email=u.email, password=u.pwd), check=400)
        self.delete("/users/"+u.email, user=self.writer)

        new_admin = dict(email=u.email, password=u.pwd, global_role='ADMIN')
        self.post("/users/", user=self.writer, json=new_admin, check=401, check_error="WRITER cannot create ADMIN")
        self.post("/users/", user=self.admin, json=new_admin)
        assert_equal(self.getuser(u, as_user=self.writer), {"email": u.email, "global_role": 'ADMIN'})
        self.delete("/users/" + u.email, user=self.writer, check=401, check_error="WRITER cannot delete ADMIN")
        self.delete("/users/" + u.email, user=self.admin)

    def test_modify_user_auth(self):
        """Are the authentication rules for changing users in place"""
        self.put('/users/unknown', check=401, check_error="Creating user should require auth")
        self.put('/users/' + self.user.email, json={'global_role': 'writer'},
                 check=401, check_error="Unprivileged users can't change their role")
        self.put('/users/' + self.writer.email, json={'email': 'new'},
                 check=401, check_error="Unprivileged users can't change other users")
        self.put('/users/' + self.user.email, json={'global_role': 'writer'},
                 check=401, check_error="Unprivileged users can't change their role")
        self.put('/users/' + self.admin.email, user=self.writer,
                 check=401, check_error="Writers can't change admins")
        self.put('/users/' + self.user.email, user=self.writer, json={'global_role': 'admin'},
                 check=401, check_error="Writers can't create admins")

    def test_modify_user(self):
        """Can we change a user"""
        u = create_user("testmail", "password")
        self.put('/users/testmail', user=u, json={'email': 'changed', 'password': 'pietje'})
        assert_equal(User.get(User.id == u.id).email, 'changed')
        assert_equal(verify_user(email='changed', password='pietje'), u)
        self.put('/users/changed', user=self.writer, json={'email': 'testmail', 'global_role': 'writer'})
        assert_equal(User.get(User.id == u.id).role, Role.WRITER)
        self.put('/users/testmail', user=self.admin, json={'global_role': 'admin'})
        assert_equal(User.get(User.id == u.id).role, Role.ADMIN)
