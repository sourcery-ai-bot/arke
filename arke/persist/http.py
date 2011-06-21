
import logging

import eventlet
httplib = eventlet.import_patched('httplib')

from .base import ipersist

class http_backend(ipersist):
    content_type = {'json': 'application/json',
                    'extjson': 'application/extjson'}

    def __init__(self, *args, **kwargs):
        super(http_backend, self).__init__(*args, **kwargs)
        self.host = self.config.get(self.section, 'host')
        self.port = None
        if self.config.has_option(self.section, 'port'):
            self.port = self.config.get(self.section, 'port')
        if self.config.has_option('core', 'debug'):
            self.debug = self.config.getboolean('core', 'debug')
        else:
            self.debug = False

    def get_connection(self):
        return httplib.HTTPConnection(self.host, self.port)

    def write(self, sourcetype, timestamp, data, hostname, extra):
        conn = self.get_connection()
        uri = '/store/%s/%s/%s' % (hostname, sourcetype, timestamp)

        assert type(extra) is dict
        headers = extra
        if headers.get('ctype', None) and "Content-type" not in headers:
            headers['Content-type'] = self.content_type[headers['ctype']]

        conn.request('PUT', uri, body=data, headers=headers)
        resp = conn.getresponse()

        if self.debug:
            assert resp.status == 200
        if resp.status == 200:
            return True
        else:
            logging.warning("Didn't get 200 from remote server!")
            return False

