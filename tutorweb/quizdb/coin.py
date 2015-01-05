import base64
import json
import random
import string
import urllib2

from zExceptions import BadRequest

import coin_config


def getBlockCount():
    return callMethod('getblockcount')


def sendTransaction(walletId, coinOwed):
    """Send coinOwed to walletId, return tx id if worked"""
    if walletId.startswith('$$UNITTEST'):
        # Unit test wallets don't do anything
        return 'UNITTESTTX:%s:%d' % (walletId, coinOwed)

    if coin_config.RPC_WALLETPASS:
        callMethod('walletpassphrase', coin_config.RPC_WALLETPASS, 2)
    return callMethod(
        'sendtoaddress',
        walletId,
        float(coinOwed) / 1000,
        "Award from tutorweb",
    )


def callMethod(method, *params):
    """Call any JSON-RPC method"""
    callId = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(5))

    request = urllib2.Request('http://%s:%d' % (
        coin_config.RPC_HOST,
        coin_config.RPC_PORT,
    ), json.dumps(dict(
        jsonrpc="1.0",
        id=callId,
        method=method,
        params=params,
    )), {
        "Authorization": "Basic " + base64.encodestring('%s:%s' % (
            coin_config.RPC_USER,
            coin_config.RPC_PASS,
        )).replace('\n', ''),
        "Content-Type": "application/json",
    })

    # Do the request, parse response
    try:
        response = urllib2.urlopen(request)
        out = json.loads(response.read())
    except urllib2.HTTPError as e:
        out = json.loads(e.read())
        if not out['error']:
            out['error'] = dict(message='', code=e.code)

    if out['id'] != callId:
        raise ValueError("Response ID %s doesn't match %s" % (out['id'], callId))

    if out['error'] is None:
        return out['result']

    if out['error']['message'] == "Invalid Smileycoin address":
        raise BadRequest(out['error']['message'])

    raise ValueError("%s (%d)" % (out['error']['message'], out['error']['code']))
