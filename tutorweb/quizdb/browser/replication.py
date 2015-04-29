import datetime

from ..replication.dump import dumpDateRange
from .base import JSONBrowserView

class ReplicationDumpView(JSONBrowserView):
    """Dump out the data from given dates"""

    def asDict(self, data={}):
        if 'HTTP_X_FORWARDED_FOR' in self.request.environ or \
                self.request.environ['REMOTE_ADDR'] != '127.0.0.1':
            raise ValueError("Only for use in scripts")

        return dumpDateRange(
            datetime.datetime.strptime(data.get('from', ''), '%Y-%m-%d'),
            datetime.datetime.strptime(data.get('to', ''), '%Y-%m-%d'),
        )
