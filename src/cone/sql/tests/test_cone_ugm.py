from cone.sql import testing
from cone.ugm.tests import test_browser_actions
from cone.ugm.tests import test_browser_autoincrement
from cone.ugm.tests import test_browser_expires
from cone.ugm.tests import test_browser_group
from cone.ugm.tests import test_browser_groups
from cone.ugm.tests import test_browser_portrait
from cone.ugm.tests import test_browser_principal
from cone.ugm.tests import test_browser_remote
from cone.ugm.tests import test_browser_roles
from cone.ugm.tests import test_browser_root
from cone.ugm.tests import test_browser_settings
from cone.ugm.tests import test_browser_user
from cone.ugm.tests import test_browser_users
from cone.ugm.tests import test_browser_utils
from cone.ugm.tests import test_layout
from cone.ugm.tests import test_localmanager
from cone.ugm.tests import test_model_group
from cone.ugm.tests import test_model_groups
from cone.ugm.tests import test_model_user
from cone.ugm.tests import test_model_users
from cone.ugm.tests import test_settings
from cone.ugm.tests import test_utils


class TestLayout(test_layout.TestLayout):
    pass


class TestModelLocalmanager(test_localmanager.TestModelLocalmanager):
    layer = testing.sql_layer


class TestModelSettings(test_settings.TestModelSettings):
    layer = testing.sql_layer


class TestModelUtils(test_utils.TestModelUtils):
    layer = testing.sql_layer


class TestModelGroup(test_model_group.TestModelGroup):
    layer = testing.sql_layer


class TestModelGroups(test_model_groups.TestModelGroups):
    layer = testing.sql_layer


class TestModelUser(test_model_user.TestModelUser):
    layer = testing.sql_layer


class TestModelUsers(test_model_users.TestModelUsers):
    layer = testing.sql_layer


class TestBrowserActions(test_browser_actions.TestBrowserActions):
    layer = testing.sql_layer


class TestBrowserAutoincrement(test_browser_autoincrement.TestBrowserAutoincrement):
    layer = testing.sql_layer


class TestBrowserExpires(test_browser_expires.TestBrowserExpires):
    layer = testing.sql_layer


class TestBrowserGroup(test_browser_group.TestBrowserGroup):
    layer = testing.sql_layer


class TestBrowserGroups(test_browser_groups.TestBrowserGroups):
    layer = testing.sql_layer


class TestBrowserPortrait(test_browser_portrait.TestBrowserPortrait):
    layer = testing.sql_layer


class TestBrowserPrincipal(test_browser_principal.TestBrowserPrincipal):
    layer = testing.sql_layer


class TestBrowserRemote(test_browser_remote.TestBrowserRemote):
    layer = testing.sql_layer


class TestBrowserRoles(test_browser_roles.TestBrowserRoles):
    layer = testing.sql_layer


class TestBrowserRoot(test_browser_root.TestBrowserRoot):
    layer = testing.sql_layer


class TestBrowserSettings(test_browser_settings.TestBrowserSettings):
    layer = testing.sql_layer


class TestBrowserUser(test_browser_user.TestBrowserUser):
    layer = testing.sql_layer


class TestBroeserUsers(test_browser_users.TestBrowserUsers):
    layer = testing.sql_layer


class TestBrowserUtils(test_browser_utils.TestBrowserUtils):
    layer = testing.sql_layer
