from App.config import getConfiguration


class ConfigObject(object):
    pass


def getConfigKey(name, product_name='tutorweb.quizdb'):
    """Fetch from product config"""
    product_config = getattr(getConfiguration(), 'product_config', {})
    if product_name not in product_config:
        raise RuntimeError("%s not in zope.conf. Edit buildout config" % product_name)
    try:
        return product_config[product_name].get(name)
    except:
        raise RuntimeError("%s was misconfigured, %s missing from zope.conf. Edit buildout config" % (
            product_name,
            name,
        ))


coin_config = ConfigObject()
coin_config.RPC_HOST = getConfigKey('coin-rpc-host')
coin_config.RPC_PORT = int(getConfigKey('coin-rpc-port'))
coin_config.RPC_USER = getConfigKey('coin-rpc-user')
coin_config.RPC_PASS = getConfigKey('coin-rpc-pass')
coin_config.RPC_WALLETPASS = getConfigKey('coin-rpc-walletpass')
coin_config.CAPTCHA_KEY = getConfigKey('coin-captcha-key')
