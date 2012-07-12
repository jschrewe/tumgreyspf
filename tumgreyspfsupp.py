#!/usr/bin/env python
#
#  Copyright (c) 2004-2007, Sean Reifschneider, tummy.com, ltd.
#  All Rights Reserved.

S_rcsid = '$Id: tumgreyspfsupp.py,v 1.8 2007-06-10 01:11:11 jafo Exp $'

import syslog, os, sys, ipaddr, re #, urllib
from pymongo import Connection, DESCENDING
from collections import MutableMapping


#  default values
default_config_file = '/Users/jschrewe/webdesign/tumgreyspf/tumgreyspf.conf'

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
        return [ipaddr.ip_network(i) for i in ips]
        
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
    
    config_file = default_config_file
    if len(sys.argv) > 1:
        if sys.argv[1] in ['-?', '--help', '-h',]:
            print 'usage: %s [<configfilename>]' % sys.argv[0]
            sys.exit(1)
            
        config_file = sys.argv[1]
    
    config = load_config(filename=config_file, config={}, use_syslog=use_syslog, use_stderr=use_stderr)
    db = DbConnection(config)
    
    return config, db


####################
#def quoteAddress(s):
#    '''Quote an address so that it's safe to store in the file-system.
#    Address can either be a domain name, or local part.
#    Returns the quoted address.'''
#
#    s = urllib.quote(s, '@_-+')
#    if len(s) > 0 and s[0] == '.': 
#        s = '%2e' + s[1:]
#    return s
#
#
#######################
#def unquoteAddress(s):
#    '''Undo the quoting of an address.  Returns the unquoted address.'''
#
#    return urllib.unquote(s)

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

###############################################################
#commentRx = re.compile(r'^(.*)#.*$')
#
#def readConfigFile(path, configData={}, configGlobal={}):
#    '''Reads a configuration file from the specified path, merging it
#    with the configuration data specified in configData.  Returns a
#    dictionary of name/value pairs based on configData and the values
#    read from path.'''
#    
#    configGlobal.log_msg('readConfigFile: Loading "%s"' % path, 3)
#    
#    nameConversion = {
#        'SPFSEEDONLY' : bool,
#        'GREYLISTTIME' : int,
#        'CHECKERS' : str,
#        'OTHERCONFIGS' : str,
#        'GREYLISTEXPIREDAYS' : float,
#    }
#
#    try:
#        fp = open(path, 'r')
#    except IOError, e:
#        syslog.syslog('ERROR: Couldn\'t open config file"%s": %s' % (path, str(e)))
#        return configData
#
#    for line in fp:
#        # ignore comments
#        line = line.split('#', 1)[0].strip()
#        if not line: 
#            continue
#        
#        try:
#            name, value = line.split('=', 1)
#        except ValueError:
#            syslog.syslog('ERROR parsing line "%s" from file "%s"' % (line, path))
#            continue
#        
#        name = name.strip()
#        value = value.strip()
#
#        #  check validity of name
#        try:
#            conversion = nameConversion[name]
#        except KeyError:
#            syslog.syslog('ERROR: Unknown name "%s" in file "%s"' % (name, path))
#            continue
#
#        configGlobal.log_msg('readConfigFile: Found entry "%s=%s"' % (name, value), 4)
#            
#        configData[name] = conversion(value)
#        
#    fp.close()
#    
#    return configData


#####################################################
#def lookupConfig(configPath, msgData, configGlobal):
#    '''Given a path, load the configuration as dictated by the
#    msgData information.  Returns a dictionary of name/value pairs.'''
#
#    #  set up default config
#    configData = {
#        'SPFSEEDONLY': configGlobal['defaultSeedOnly'],
#        'GREYLISTTIME': configGlobal['defaultAllowTime'],
#        'CHECKGREYLIST': 1,
#        'CHECKSPF': 1,
#        'OTHERCONFIGS': 'envelope_sender,envelope_recipient',
#    }
#
#    #  load directory-based config information
#    if configPath[:8] != 'file:///':
#        syslog.syslog('ERROR: Unknown path type in: "%s", using defaults' % msgData)
#        return configData
#        
#    configGlobal.log_msg('lookupConfig: Starting file lookup from "%s"' % configPath, 3)
#        
#    basePath = configPath[7:]
#    configData = {}
#
#    #  load default config
#    path = os.path.join(basePath, '__default__')
#    
#    if os.path.exists(path):
#        configGlobal.log_msg('lookupConfig: Loading default config: "%s"' % path, 3)
#        configData = readConfigFile(path, configData, configGlobal)
#    else:
#        syslog.syslog('lookupConfig: No default config found in "%s", this is probably an install problem.' % path)
#
#    # check if other configs need to be loaded
#    otherConfigs = configData.get('OTHERCONFIGS', '').split(',')
#    if not otherConfigs or otherConfigs == ['']: 
#        return configData
#    
#    configGlobal.log_msg('lookupConfig: Starting load of configs: "%s"' % str(otherConfigs), 3)
#
#    #  load other configs from OTHERCONFIGS
#    configsAlreadyLoaded = []
#        
#    #  SENDER/RECIPIENT
#    for cfgType in otherConfigs:
#        cfgType = cfgType.strip()
#
#        #  skip if already loaded
#        if cfgType in configsAlreadyLoaded: 
#            continue
#            
#        configsAlreadyLoaded + [cfgType] 
#        configGlobal.log_msg('lookupConfig: Trying config "%s"' % cfgType, 3) 
#
#        #  SENDER/RECIPIENT
#        if cfgType == 'envelope_sender' or cfgType == 'envelope_recipient':
#            #  get address
#            if cfgType == 'envelope_sender': 
#                address_key = 'sender'
#            else: 
#                address_key = 'recipient'
#                
#            try:
#                address = msgData[address_key]
#            except KeyError:
#                configGlobal.log_msg('lookupConfig: Could not find %s' % cfgType, 2) 
#                continue
#
#            #  split address into domain and local
#            try:
#                local, domain = address.split('@', 1)
#            except ValueError:
#                configGlobal.log_msg('lookupConfig: Could not find %s address '
#                                    'from "%s", skipping' % (cfgType, address), 2) 
#                continue
#            local = quoteAddress(local)
#            domain = quoteAddress(domain)
#
#            #  load configs
#            path = os.path.join(basePath, cfgType)
#            domainPath = os.path.join(path, domain, '__default__')
#            localPath = os.path.join(path, domain, local)
#            for name in [domainPath, localPath]:
#                configGlobal.log_msg('lookupConfig: Trying file "%s"' % name, 3) 
#                if os.path.exists(name):
#                    configData = readConfigFile(name, configData, configGlobal)
#
#        #  CLIENT IP ADDRESS
#        elif cfgType == 'client_address':
#            try:
#                ip = msgData['client_address']
#            except KeyError:
#                configGlobal.log_msg('lookupConfig: Could not find client address', 2) 
#                continue
#            
#            path = basePath
#            for name in ['client_address', ] + ip.split('.'):
#                path = os.path.join(path, name)
#                defaultPath = os.path.join(path, '__default__')
#                configGlobal.log_msg('lookupConfig: Trying file "%s"' % defaultPath, 3) 
#                if os.path.exists(defaultPath):
#                    configData = readConfigFile(defaultPath, configData, configGlobal)
#            configGlobal.log_msg('lookupConfig: Trying file "%s"' % path, 3) 
#            if os.path.exists(path):
#                configData = readConfigFile(path, configData, configGlobal)
#
#            #  unknown configuration type
#        else:
#            syslog.syslog('ERROR: Unknown configuration type: "%s"' % cfgType)
#
#    return configData
