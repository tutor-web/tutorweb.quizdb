import datetime

from ..replication.dump import dumpDateRange
from ..replication.ingest import ingestDateRange, updateHost
from .base import JSONBrowserView

class ReplicationDumpView(JSONBrowserView):
    """Dump out the data from given dates"""

    def asDict(self, data={}):
        if 'HTTP_X_FORWARDED_FOR' in self.request.environ or \
                self.request.environ['REMOTE_ADDR'] != '127.0.0.1':
            raise ValueError("Only for use in scripts")  # TODO: 403?

        return dumpDateRange(
            datetime.datetime.strptime(data.get('from', ''), '%Y-%m-%d'),
            datetime.datetime.strptime(data.get('to', ''), '%Y-%m-%d'),
        )

class ReplicationIngestView(JSONBrowserView):
    """Dump out the data from given dates"""

    def asDict(self, data={}):
        if 'HTTP_X_FORWARDED_FOR' in self.request.environ or \
                self.request.environ['REMOTE_ADDR'] != '127.0.0.1':
            raise ValueError("Only for use in scripts")

        return ingestDateRange(data)

class ReplicationUpdateHostView(JSONBrowserView):
    """Update / add the host"""

    def asDict(self, data={}):
        if 'fqdn' not in data:
            raise ValueError("fqdn missing, should be a host name")
        if 'hostKey' not in data:
            raise ValueError("fqdn missing, should be a UUID")
        return updateHost(data['fqdn'], data['hostKey'])
