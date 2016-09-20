import logging
import pprint

from .base import JSONBrowserView

logger = logging.getLogger(__package__)

class LogErrorView(JSONBrowserView):
    def asDict(self, data):
        pp = pprint.PrettyPrinter(indent=2)

        logger.warn(
            "Clientside error (user-agent: %s):\n%s",
            self.request.get('HTTP_USER_AGENT') or 'unknown',
            pp.pformat(data),
        )
        return dict(logged=True)
