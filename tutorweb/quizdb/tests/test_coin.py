import sys
import base64
import json
from StringIO import StringIO
import unittest
import urllib2

from zExceptions import BadRequest

class CoinConfig(object):
    RPC_HOST = "moohost"
    RPC_PORT = 900
    RPC_USER = "smly"
    RPC_PASS = "realgoodpassword"
    RPC_WALLETPASS = None
class FakeConfig(object):
    coin_config = CoinConfig()
sys.modules["tutorweb.quizdb.config"] = FakeConfig

from .. import coin


class TestCoin(unittest.TestCase):
    def tearDown(self):
        chooseOpener()

    def test_utTransactions(self):
        """Unit-test transactions do nothing"""
        chooseOpener(NoHTTPHandler)

        self.assertEqual(
            coin.sendTransaction('$$UNITTEST01', 99),
            "UNITTESTTX:$$UNITTEST01:99",
        )

    def test_realTransaction(self):
        """Requests get properly encoded"""
        chooseOpener(MockHTTPHandler)
        global nextResponse

        # Configure with usless settings
        coin.coin_config.RPC_HOST = "moohost"
        coin.coin_config.RPC_PORT = 900
        coin.coin_config.RPC_USER = "smly"
        coin.coin_config.RPC_PASS = "realgoodpassword"
        coin.coin_config.RPC_WALLETPASS = None

        nextResponse = dict(result=1234)
        self.assertEqual(coin.sendTransaction('WaLlEt', 23), 1234)
        self.assertEqual(requests[-1], dict(
            url='http://moohost:900',
            contenttype='application/json',
            auth='smly:realgoodpassword',
            data=dict(
                id=requests[-1]['data']['id'],
                jsonrpc=u'1.0',
                method=u'sendtoaddress',
                params=[u'WaLlEt', 0.023, u'Award from tutorweb'],
            ),
        ))

        # Try another transaction
        nextResponse = dict(result=8421)
        self.assertEqual(coin.sendTransaction('WALL-E', 84), 8421)
        self.assertEqual(requests[-1], dict(
            url='http://moohost:900',
            contenttype='application/json',
            auth='smly:realgoodpassword',
            data=dict(
                id=requests[-1]['data']['id'],
                jsonrpc=u'1.0',
                method=u'sendtoaddress',
                params=[u'WALL-E', 0.084, u'Award from tutorweb'],
            ),
        ))

        # IDs shouldn't match
        for i in range(100):
            self.assertEqual(coin.sendTransaction('WALL-E', 84), 1234)
        self.assertEqual(
            len([r['data']['id'] for r in requests]),
            len(set([r['data']['id'] for r in requests])),
        )

    def test_errorTransaction(self):
        """Test failures fail"""
        chooseOpener(MockHTTPHandler)
        global nextResponse
        
        # General failure
        nextResponse = dict(error=dict(message="oh noes", code=-42))
        with self.assertRaisesRegexp(ValueError, "oh noes \(\-42\)"):
            coin.sendTransaction('WALL-E', 84)

        # Mismatching response ID
        nextResponse = dict(id="camel")
        with self.assertRaisesRegexp(ValueError, "camel"):
            coin.sendTransaction('WALL-E', 84)

        # Invalid address
        nextResponse = dict(error=dict(message="Invalid Smileycoin address", code=-5))
        with self.assertRaisesRegexp(BadRequest, "Smileycoin"):
            coin.sendTransaction('WALL-E', 84)

    def test_walletOpening(self):
        """Wallets can be opened first"""
        chooseOpener(MockHTTPHandler)
        global nextResponse

        # Configure with usless settings
        coin.coin_config.RPC_HOST = "moohost"
        coin.coin_config.RPC_PORT = 900
        coin.coin_config.RPC_USER = "smelly"
        coin.coin_config.RPC_PASS = "badpassword"
        coin.coin_config.RPC_WALLETPASS = "letmein"

        self.assertEqual(coin.sendTransaction('WaLlEt', 23), 1234)
        self.assertEqual(requests[-2], dict(
            url='http://moohost:900',
            contenttype='application/json',
            auth='smelly:badpassword',
            data=dict(
                id=requests[-2]['data']['id'],
                jsonrpc=u'1.0',
                method=u'walletpassphrase',
                params=['letmein', 2],
            ),
        ))
        self.assertEqual(requests[-1], dict(
            url='http://moohost:900',
            contenttype='application/json',
            auth='smelly:badpassword',
            data=dict(
                id=requests[-1]['data']['id'],
                jsonrpc=u'1.0',
                method=u'sendtoaddress',
                params=[u'WaLlEt', 0.023, u'Award from tutorweb'],
            ),
        ))


class NoHTTPHandler(urllib2.HTTPHandler):
    def http_open(self, req):
        raise ValueError("I said no HTTP")


requests = []
nextResponse = {}


class MockHTTPHandler(urllib2.HTTPHandler):
    def http_open(self, req):
        requests.append(dict(
            url=req.get_full_url(),
            contenttype=req.headers['Content-type'],
            auth=base64.decodestring(req.headers['Authorization'].replace('Basic ', '')),
            data=json.loads(req.data),
        ))

        # Sanitise response
        global nextResponse
        if 'id' not in nextResponse:
            nextResponse['id'] = requests[-1]['data']['id']
        if 'error' not in nextResponse:
            nextResponse['error'] = None
        if 'result' not in nextResponse:
            nextResponse['result'] = 1234

        resp = urllib2.addinfourl(
            StringIO(json.dumps(nextResponse)),
            "Message of some form",
            req.get_full_url(),
        )
        resp.code = 200
        resp.msg = "OK"
        nextResponse = dict()
        return resp


def chooseOpener(klass=None):
    if klass is None:
        opener = urllib2.build_opener()
    else:
        opener = urllib2.build_opener(klass)
    urllib2.install_opener(opener)
