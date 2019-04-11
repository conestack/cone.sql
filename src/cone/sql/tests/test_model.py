from node.tests import NodeTestCase
from cone.sql import testing


class TestModel(NodeTestCase):
    layer = testing.sql_layer

    def test_foo(self):
        pass