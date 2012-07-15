#!/usr/bin/env python
#
#  Copyright (c) 2004-2007, Sean Reifschneider, tummy.com, ltd.
#  All Rights Reserved.
#
#  Jan Schrewe <jan@schafproductions.com>, 2012

import syslog, os, sys, re
from pymongo import Connection, DESCENDING
from collections import MutableMapping, MutableSequence

try:
    from ipaddr import ip_network
except ImportError:
    # No PEP 3144 interface yet. Fall back.
    from ipaddr import IPNetwork
    ip_network = IPNetwork

#  default values
default_config_file = '/etc/tumgreyspf/tumgreyspf.conf'

default_config = {
    'debugLevel': 0,
    'defaultSeedOnly': False,
    'greylistTime': 600,
    'ignoreLastByte': True,
    'greylistByIPOnly': False,
    'spfAcceptOnPermError': True,
    'spfBypassGreylist': False,
    'greylistExpireDays': 10.0,
    'checkers': ['spf', 'greylist', ],
    'spfSeedOnly': False,
    'dbHost': 'localhost',
    'dbPort': '',
    'databaseName': 'tumgreyspf',
}

# These addresses are always inserted into all whitelists
# You can add adresses that should be whitelisted here,
# but you *should* use the tumgreyspf-whitelist tool.
default_whitelist = ['127.0.0.0/8', '::ffff:127.0.0.0/104', '::1/128', ]

class ParseException(Exception):
    pass

class DataDict(dict):
    """
    Used to parse and store data provided by postfix.
    The get method provides a sane default for output.
    """
    _line_re = re.compile(r'^\s*([^=\s]+)\s*=(.*)$')
    _preserve_vals = ['protocol_state', 'protocol_name', 'queue_id',]
    
    def get(self, key, default='<UNKNOWN>'):
        return super(DataDict, self).get(key, default)
    
    def parse_line(self, line):
        m = self._line_re.match(line)
        if m is None:
            raise ParseException('ERROR: Could not match line "%s"' % line)
        
        key = m.group(1)
        value = m.group(2)
        if key not in self._preserve_vals:
            value = value.lower()
        self[key] = value

class WhiteList(MutableSequence):
    """
    Lazily loads whiltelists on access. Behaves like a normal
    python list.
    """
    _data = None
    _default = None
    
    def __init__(self, db, collection, default=None):
        self._db = db
        self._coll = collection
        if default is not None:
            self._default = [ip_network(n) for n in default]
    
    def _load_data(self, force=False):
        if self._data is not None and not force:
            return
        
        coll = self._db[self._coll]
        l = coll.find()
        self._data = [ip_network(d['ip'], version=d['type']) for d in l] 
        
        # if force is true chances are this function
        # was called from save or remove. To avoid problems
        # we do not try to insert any more data. 
        if self._default is None or force:
            return
        
        for d in self._default:
            if d not in self._data:
                self.append(d)
        self._default = None
        
        l = coll.find()
        self._data = [ip_network(d['ip'], version=d['type']) for d in l]
            
        
    def _save_data(self):
        coll = self._db[self._coll]
        for net in self._data:
            d = {'ip': int(net)}
            f = d.copy()
            d['type'] = net.version
            coll.update(f, d, upsert=True)
        self._load_data(force=True)
            
    def _delitem(self, item):
        f = {'ip': int(item)}
        coll = self._db[self._coll]
        coll.remove(f)
        self._load_data(force=True)
        
    def __len__(self):
        self._load_data()
        return self._data.__len__()
            
    def __getitem__(self, index):
        self._load_data()
        return self._data.__getitem__(index)
    
    def __contains__(self, value):
        self._load_data()
        return self._data.__contains__(value)
    
    def __iter__(self):
        self._load_data()
        return self._data.__iter__()
    
    def __setitem__(self, index, value):
        self._load_data()
        self._data.__setitem__(index, value)
        self._save_data()
        
    def __delitem__(self, index):
        self._load_data()
        item = self.__getitem__(index)
        self._data.__delitem__(index)
        self._delitem(item)
        
    def insert(self, index, value):
        self._load_data()
        self._data.insert(index, value)
        self._save_data()
        
    def __str__(self):
        s = ', '.join([str(i) for i in self])
        return "[%s]" % s

class ConfigException(Exception):
    '''Exception raised when there's a configuration file error.'''
    pass

def _load_config_file(file, values):
    '''Load the specified config file if it exists, raise ValueError if there
    is an error in the config file.  "values" is a dictionary of default
    config values.  "values" is modified in place, and nothing is returned.'''

    if not os.path.exists(file): 
        raise IOError

    try:
        execfile(file, {}, values)
    except Exception:
        raise ConfigException('FATAL: Error reading config file "%s": %s' % (file, sys.exc_info()[1]))


class DbConnection(object):
    """
    Wrapper for the mongo db connection.
    Connects lazily on access and can be used like a pymongo db object
    """ 
    _db = None
    host = None
    port = None
    database = None
    
    def __init__(self, config):
        self.host = config['dbHost']
        if config['dbPort']:
            try:
                self.port = int(config['dbPort'])
            except (TypeError, KeyError):
                pass
        self.database = config['databaseName']
                
    def connect(self):
        args = {}
        if self.host:
            args['host'] = self.host
        if self.port:
            args['port'] = self.port
        
        conn = Connection(**args)
        self._db = conn[self.database]

        # ensure indexes are there
        self._db.greylist.ensure_index([
            ('ip', DESCENDING),
            ('sender', DESCENDING), 
            ('recipient', DESCENDING),
        ], unique=True)

        self._db.blackhole_ips.ensure_index('ip', unique=True)
        self._db.blackhole_adresses.ensure_index('address')
        
    def __getattr__(self, attr):
        if self._db is None:
            self.connect()
        return getattr(self._db, attr)
    
    def __getitem__(self, key):
        if self._db is None:
            self.connect()
        return self._db[key]


class ConfigData(MutableMapping):
    """
    Used for the data from the config file. Provides a dict interface and
    access to the db connection. log_msg(msg, lvl=None) can be used for
    debug output which honors the debug level set in the config.
    
    Dict-style access is not case sensitive.
    """
    
    _config = {}
    _dbg_lvl = None
    _db = None
    _whitelists = {}
    
    def __init__(self, config_dict=None, use_syslog=True, use_stderr=False):
        if config_dict is None:
            self.update(default_config)
        else:
            self.update(config_dict)
            
        self.use_syslog, self.use_stderr = use_syslog, use_stderr
        
    def log_msg(self, msg, lvl=None):
        if lvl is None or self._dbg_lvl >= lvl:
            if self.use_syslog:
                syslog.syslog(msg)
            if self.use_stderr:
                sys.stderr.write(msg + '\n')
    
    @property            
    def db(self):
        if self._db is None:
            self._db = DbConnection(self)
        return self._db 
        
    def _process_checkers(self, checkers):
        return [c.strip().lower() for c in checkers]
        
    def __len__(self):
        return self._config.__len__() + self._whitelists.__len__()
    
    def __getitem__(self, key):
        key = self.__keytransform__(key)
        
        if key in ['spfwhitelist', 'greylistwhitelist',]:
            if not key in self._whitelists:
                self._whitelists[key] = WhiteList(self.db, key, default_whitelist)
            return self._whitelists[key]
        
        value = self._config.__getitem__(key)
            
        return value
    
    def __setitem__(self, key, value):
        key = self.__keytransform__(key)
            
        if key == 'checkers':
            value = self._process_checkers(value)
            
        if key == 'debugLevel':
            self._dbg_lvl = value
            
        self._config.__setitem__(key, value)
        
    def __delitem__(self, key):
        self._config.__delitem__(self.__keytransform__(key))
        
    def __iter__(self):
        for k, v in self._config.iteritems():
            yield (k, v)
        for k in ['spfwhitelist', 'greylistwhitelist',]:
            yield (k, self[k])
    
    def __contains__(self, key):
        key = self.__keytransform__(key)
        
        if key in ['spfwhitelist', 'greylistwhitelist',]:
            return True
        
        return self._config.__contains__(key)
    
    def __keytransform__(self, key):
        return key.lower()
        
        
def load_config(config={}, use_syslog=True, use_stderr=False):
    '''Load the specified config file, exit and log errors if it fails,
    otherwise return a config dictionary.'''

    conf = ConfigData(use_syslog=use_syslog, use_stderr=use_stderr)
    conf.update(config)

    def _print_and_die(msg):
        if use_syslog:
            syslog.syslog(msg)
        if use_stderr:
            sys.stderr.write('%s\n' % msg)
        sys.exit(1)

    try:
        _load_config_file(default_config_file, conf)
    except ConfigException as e:
        _print_and_die(e.args[0])
    except IOError:
        msg = "FATAL: Config file not found: %s" % default_config_file
        _print_and_die(msg)

    return conf


class ExceptHook(object):
    def __init__(self, use_syslog=True, use_stderr=False):
        self.use_syslog = use_syslog
        self.use_stderr = use_stderr
        
    def __call__(self, etype, evalue, etb):
        import traceback
        tb = traceback.format_exception(etype, evalue, etb)
        for line in tb:
            if self.use_syslog:
                syslog.syslog(line.rstrip())
            if self.use_stderr:
                sys.stderr.write(line)
    
def prepare_start(use_syslog=True, use_stderr=False):
    if use_syslog:
        syslog.openlog(os.path.basename(sys.argv[0]), syslog.LOG_PID, syslog.LOG_MAIL)
        
    sys.excepthook = ExceptHook(use_syslog, use_stderr)
    
    config = load_config(config={}, use_syslog=use_syslog, use_stderr=use_stderr)
    
    return config


class InstanceCheck(object):
    """
    Used to keep track of and check if a mail instance has
    already been seen during the life time of the application.
    """
    _instances = []
    
    def _check_instance(self, data):
        try:
            return data['instance']
        except KeyError:
            # The following if is only needed for testing.  Postfix 
            # will always provide instance.
            import random
            return str(int(random.random() * 100000))
    
    def __call__(self, data):
        instance = self._check_instance(data)
        if instance not in self._instances:
            self._instances.append(instance)
            return False
        return True


