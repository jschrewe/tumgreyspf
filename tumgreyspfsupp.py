#!/usr/bin/env python
#
#  Copyright (c) 2004-2007, Sean Reifschneider, tummy.com, ltd.
#  All Rights Reserved.

import syslog, os, sys, re
from pymongo import Connection, DESCENDING
from collections import MutableMapping

try:
    from ipaddr import ip_network
except ImportError:
    # No PEP 3144 interface yet. Fall back.
    from ipaddr import IPNetwork
    ip_network = IPNetwork

__version__ = '0.1-mongo'

#  default values
default_config_file = '/etc/tumgreyspf/tumgreyspf.conf'

default_config = {
    'debugLevel': 0,
    'defaultSeedOnly': False,
    'greylistTime': 600,
    'ignoreLastByte': True,
    'greylistByIPOnly': False,
    'spfAcceptOnPermError': True,
    'greylistExpireDays': 10.0,
    'checkers': ['spf', 'greylist', ],
    'spfSeedOnly': False,
    'spfWhiteList': ['127.0.0.0/8', '::ffff:127.0.0.0/104', '::1/128', ],
    'greylistWhiteList': ['127.0.0.0/8', '::ffff:127.0.0.0/104', '::1/128', ],
    'dbHost': 'localhost',
    'dbPort': '',
    'databaseName': 'tumgreyspf',
}

class ParseException(Exception):
    pass

class DataDict(dict):
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


class ConfigData(MutableMapping):
    _config = {}
    _dbg_lvl = None
    
    def __init__(self, config_dict=None):
        if config_dict is None:
            self.update(default_config)
        else:
            self.update(config_dict)
        
    def log_msg(self, msg, lvl=None):
        if lvl is None or self._dbg_lvl >= lvl:
            syslog.syslog(msg)
        
    def _process_ips(self, ips):
        return [ip_network(i) for i in ips]
        
    def _process_checkers(self, checkers):
        return [c.strip().lower() for c in checkers]
        
    def __len__(self):
        return self._config.__len__()
    
    def __getitem__(self, key):
        return self._config.__getitem__(self.__keytransform__(key))
    
    def __setitem__(self, key, value):
        key = self.__keytransform__(key)
        
        if key in ['spfwhitelist', 'greylistwhitelist',]:
            value = self._process_ips(value)
            
        if key == 'checkers':
            value = self._process_checkers(value)
            
        if key == 'debugLevel':
            self._dbg_lvl = value
            
        self._config.__setitem__(key, value)
        
    def __delitem__(self, key):
        self._config.__delitem__(self.__keytransform__(key))
        
    def __iter__(self):
        return self._config.__iter__()
    
    def __contains__(self, key):
        return self._config.__contains__(self.__keytransform__(key))
    
    def __keytransform__(self, key):
        return key.lower()
        
        
def load_config(filename=default_config_file, config={}, use_syslog=True, use_stderr=False):
    '''Load the specified config file, exit and log errors if it fails,
    otherwise return a config dictionary.'''

    conf = ConfigData()
    conf.update(config)

    try:
        _load_config_file(filename, conf)
    except ConfigException as e:
        if use_syslog:
            syslog.syslog(e.args[0])
        if use_stderr:
            sys.stderr.write('%s\n' % e.args[0])
        sys.exit(1)
    except IOError:
        msg = "FATAL: Config file not found: %s" % filename
        if use_syslog:
            syslog.syslog(msg)
        if use_stderr:
            sys.stderr.write('%s\n' % msg)
        sys.exit(1)

    return conf



class ExceptHook(object):
    def __init__(self, use_syslog=True, use_stderr=False):
        self.use_syslog = use_syslog
        self.use_stderr = use_stderr
        
    def __call__(self, etype, evalue, etb):
        import traceback
        tb = traceback.format_exception(etype, evalue, etb)
        for line in tb:
            line = line.rstrip()
            if self.use_syslog:
                syslog.syslog(line)
            if self.use_stderr:
                sys.stderr.write(line + '\n')
    
def prepare_start(use_syslog=True, use_stderr=False):
    sys.excepthook = ExceptHook(use_syslog, use_stderr)
    
    if use_syslog:
        syslog.openlog(os.path.basename(sys.argv[0]), syslog.LOG_PID, syslog.LOG_MAIL)
    
    config_file = default_config_file
    if len(sys.argv) > 1:
        if sys.argv[1] in ['-?', '--help', '-h',]:
            
            print 'usage: %s [<configfilename>]' % os.path.basename(sys.argv[0])
            sys.exit(1)
            
        config_file = sys.argv[1]
    
    config = load_config(filename=config_file, config={}, use_syslog=use_syslog, use_stderr=use_stderr)
    db = DbConnection(config)
    
    return config, db


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

class InstanceCheck(object):
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


