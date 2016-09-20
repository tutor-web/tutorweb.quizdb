import logging
import pprint

from .base import JSONBrowserView

logger = logging.getLogger(__package__)

class LogErrorView(JSONBrowserView):
    def asDict(self, data):
        pp = pprint.PrettyPrinter(indent=2)

        logger.warn("Clientside error:\n%s", pp.pformat(data))
        return dict(logged=True)
