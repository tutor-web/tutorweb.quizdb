import logging
import pprint

from .base import JSONBrowserView

logger = logging.getLogger(__package__)

class LogErrorView(JSONBrowserView):
    def asDict(self, data):
        pp = pprint.PrettyPrinter(indent=2)
        messages = []

        membership = self.context.portal_membership
        if membership.isAnonymousUser():
            messages.append('unauth')
        else:
            mb = membership.getAuthenticatedMember()
            messages.append('user: "%s"' % mb.getUserName())

        messages.append('user-agent: "%s"' % (self.request.get('HTTP_USER_AGENT', None) or 'unknown'))

        logger.warn(
            'Clientside error %s:\n%s',
            ' '.join('(%s)' % m for m in messages),
            pp.pformat(data),
        )
        return dict(logged=True)
