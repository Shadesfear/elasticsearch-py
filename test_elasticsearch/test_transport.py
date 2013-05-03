from unittest import TestCase

from elasticsearch.transport import Transport
from elasticsearch.connection import Connection
from elasticsearch.exceptions import TransportError

class DummyConnection(Connection):
    def __init__(self, **kwargs):
        self.exception = kwargs.pop('exception', None)
        self.status, self.data = kwargs.pop('status', 200), kwargs.pop('data', '{}')
        self.calls = []
        super(DummyConnection, self).__init__(**kwargs)

    def perform_request(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.exception:
            raise self.exception
        return self.status, self.data

CLUSTER_NODES = '''{
    "ok" : true,
    "cluster_name" : "super_cluster",
    "nodes" : {
        "wE_6OGBNSjGksbONNncIbg" : {
            "name" : "Nightwind",
            "transport_address" : "inet[/127.0.0.1:9300]",
            "hostname" : "wind",
            "version" : "0.20.4",
            "http_address" : "inet[/1.1.1.1:123]"
        }
    }
}'''

class TestTransport(TestCase):
    def test_kwargs_passed_on_to_connections(self):
        t = Transport([{'host': 'google.com'}], port=123)
        self.assertEquals(1, len(t.connection_pool.connections))
        self.assertEquals('http://google.com:123', t.connection_pool.connections[0].host)

    def test_kwargs_passed_on_to_connection_pool(self):
        dt = object()
        t = Transport([{}], dead_timeout=dt)
        self.assertIs(dt, t.connection_pool.dead_timeout)

    def test_custom_connection_class(self):
        class MyConnection(object):
            def __init__(self, **kwargs):
                self.kwargs = kwargs
        t = Transport([{}], connection_class=MyConnection)
        self.assertEquals(1, len(t.connection_pool.connections))
        self.assertIsInstance(t.connection_pool.connections[0], MyConnection)

    def test_add_connection(self):
        t = Transport([{}], randomize_hosts=False)
        t.add_connection({"host": "google.com"})

        self.assertEquals(2, len(t.connection_pool.connections))
        self.assertEquals('http://google.com:9200', t.connection_pool.connections[1].host)

    def test_request_will_fail_after_X_retries(self):
        t = Transport([{'exception': TransportError('abandon ship')}], connection_class=DummyConnection)

        self.assertRaises(TransportError, t.perform_request, 'GET', '/')
        self.assertEquals(3, len(t.get_connection().calls))

    def test_failed_connection_will_be_marked_as_dead(self):
        t = Transport([{'exception': TransportError('abandon ship')}], connection_class=DummyConnection)

        self.assertRaises(TransportError, t.perform_request, 'GET', '/')
        self.assertEquals(0, len(t.connection_pool.connections))

    def test_sniff_on_start_fetches_and_uses_nodes_list(self):
        t = Transport([{'data': CLUSTER_NODES}], connection_class=DummyConnection, sniff_on_start=True)
        self.assertEquals(1, len(t.connection_pool.connections))
        self.assertEquals('http://1.1.1.1:123', t.get_connection().host)

    def test_sniff_on_fail_triggers_sniffing_on_fail(self):
        t = Transport([{'exception': TransportError('abandon ship')}, {"data": CLUSTER_NODES}],
            connection_class=DummyConnection, sniff_on_connection_fail=True, max_retries=1, randomize_hosts=False)

        self.assertRaises(TransportError, t.perform_request, 'GET', '/')
        self.assertEquals(1, len(t.connection_pool.connections))
        self.assertEquals('http://1.1.1.1:123', t.get_connection().host)

    def test_sniff_after_n_requests(self):
        t = Transport([{"data": CLUSTER_NODES}],
            connection_class=DummyConnection, sniff_after_requests=5)

        for _ in range(4):
            t.perform_request('GET', '/')
        self.assertEquals(1, len(t.connection_pool.connections))
        self.assertIsInstance(t.get_connection(), DummyConnection)

        t.perform_request('GET', '/')
        self.assertEquals(1, len(t.connection_pool.connections))
        self.assertEquals('http://1.1.1.1:123', t.get_connection().host)

    def test_sniff_on_failure_shortens_sniff_after_n_requests(self):
        t = Transport([{'exception': TransportError('abandon ship')}, {"data": CLUSTER_NODES}],
            connection_class=DummyConnection, sniff_on_connection_fail=True, max_retries=1,
            randomize_hosts=False, sniff_after_requests=4)

        self.assertRaises(TransportError, t.perform_request, 'GET', '/')
        self.assertEquals(1, len(t.connection_pool.connections))
        self.assertEquals('http://1.1.1.1:123', t.get_connection().host)
        self.assertEquals(3, t.sniff_after_requests)
