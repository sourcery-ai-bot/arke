
from os import makedirs, remove, listdir
from os.path import basename, isdir, exists, join as path_join
from json import dumps as json_dumps
from time import time
import logging
from Queue import Empty
from threading import Lock, Condition
from collections import deque

logger = logging.getLogger(__name__)

from bson.json_util import default as json_util_default

MAX_SPOOL_FILE_SIZE = 1024 * 1024 * 1

def get_sourcetype_from_filename(fname):
    if isinstance(fname, file):
        fname = fname.name
    fname = basename(fname)
    return fname[:fname.rindex('_')]

class Spooler(object):
    def __init__(self, config):
        self.config = config
        self.spool_dir = config.get('core', 'spool_dir')
        if not isdir(self.spool_dir):
            assert not exists(self.spool_dir), "specified spool_dir %s already exists, and isn't a dir!" % self.spool_dir
            makedirs(self.spool_dir)
        self._file_registry = {}
        self._sourcetype_registry = []
        self._queue = deque(self.keys())
        self._lock = Lock()
        self._not_empty = Condition(self._lock)

    def _open(self, sourcetype):
        if sourcetype not in self._sourcetype_registry:
            self._sourcetype_registry.append(sourcetype)
        fname = path_join(self._spool_dir, '%s_%f' % (sourcetype, time()))
        self._file_registry[sourcetype] = open(fname, 'a')

    def _get_file(self, sourcetype):
        if sourcetype not in self._file_registry:
            self._open(sourcetype)
        return self._file_registry[sourcetype]

    def keys(self):
        spool_dir = self.spool_dir
        return (path_join(spool_dir, f) for f in listdir(spool_dir))

    def items(self):
        return ((f, open(f, 'r')) for f in self.keys())

    def values(self):
        return (v for k,v in self.items())

    def close(self):
        def _close(fh):
            fh.flush()
            fh.close()
        map(_close, self._file_registry.values())

    def append(self, sourcetype, timestamp, data, extra):
        s = json_dumps([timestamp, data], default=json_util_default)

        with self._lock:
            _f = self._get_file(sourcetype)
            if not _f.tell():
                #new file, needs metadata
                hostname = self.config.get('core', 'hostname')
                m = json_dumps([hostname, sourcetype, extra],
                               default=json_util_default)
                _f.write(str(len(m)) + '\n' + m)

            _f.write(str(len(s)) + '\n' + s)
            if _f.tell() > MAX_SPOOL_FILE_SIZE:
                _f.flush()
                _f.close()
                self._file_registry.pop(sourcetype)
                self._queue.append(_f.name)

        self._not_empty.notify()

    def delete(self, file_handle):
        fn = file_handle.name
        logger.debug("Deleting spool file %s" % fn)
        file_handle.close()
        remove(fn)

    def get(self, timeout=None):
        if self._queue:
            _f = open(self._queue.pop(), 'r')
            logger.debug("Returning spool_file %s from spooler queue." % _f.name)
            return _f

        with self._not_empty as ne_cond:

            not_empty = filter(lambda x: self._get_file(x).tell(),
                               self._sourcetype_registry)

            if not not_empty:
                if timeout is None:
                    raise Empty

                assert isinstance(timeout, int) and timeout > 0
                endtime = time() + timeout
                while not not_empty or not self._queue:
                    remaining = endtime - time()
                    if remaining <= 0.0:
                        raise Empty
                    ne_cond.wait(remaining)
                    not_empty = filter(lambda x: self._get_file(x).tell(),
                                       self._sourcetype_registry)

                if self._queue:
                    _f = open(self._queue.pop(), 'r')
                    logger.debug("Returning spool_file %s from spooler queue." % _f.name)
                    return _f

            sourcetype = not_empty[0]
            _f = self._file_registry.pop(sourcetype)
            _f.flush()
            fname = _f.name
            _f.close()
            sr = self._sourcetype_registry
            sr.append( sr.pop( sr.index( sourcetype )))
            logger.debug("Returning spool_file %s from spooler active registry." % _f.name)
            return open(fname, 'r')

