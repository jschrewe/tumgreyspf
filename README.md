# tumgreyspf README

Sean Reifschneider <jafo@tummy.com>
**Homepage:** http://www.tummy.com/Community/software/tumgreyspf/
**Code/bugfixes:** https://github.com/linsomniac/tumgreyspf

--------------------------------------------------------------

This is tumgreyspf, an external policy checker for the postfix mail
server.  It can optionally greylist and/or use spfquery to check SPF
records to determine if email should be accepted by your server.

It uses the file-system as it's database, no additional database is
required to use it.

## LICENSE

   tumgreyspf is licensed under the GPL.

## BENEFITS

### High Accuracy

SPF is information published by the domain owner about what systems
may legitimately send e-mail for the domain.  Greylisting takes
advantage of spam and viruses that do not follow the RFCs and retry
deliveries on temporary failure.  We use these checks as part of our
mail system and have seen several orders of magnitude reduction in
spam, lower system load, and few problems with legitimate mail
getting blocked.

### Low Maintenance

tumgreyspf requires no regular attention from the administrator to
remain effective.

### Easy Setup

Installation should be as easy as installing an RPM or Debian package
on your system.  There are few additional requirements.  Extensive
time has been devoted to installation automation and documentation.

## REQUIREMENTS

   * [Python](http://www.python.org/)

   * [Postfix 2.1 or above](http://www.postfix.org/)

   * *Optional:* [spfquery](http://spf.pobox.com/downloads.html) or [pyspf](http://www.wayforward.net/spf/)

## NOTE BEFORE YOU USE TUMGREYSPF

tumgreyspf stores the greylist data in the file-system using many small
files.  This has a few benefits, namely that you do not need to install
or configure any database software.  It also makes you immune to to
database corruption issues that other greylist systems have.

However, this does mean that if not configured properly you may
experience extremely poor performance. There are details in one of my
blog posts:

    http://www.tummy.com/journals/entries/jafo_20051001_003419

However, the short answer is that you need to be careful about blocking
known bad recipient and sender addresses in Postfix before handing
messages off to tumgreyspf, and you probably should configure SPF to be
checked before greylisting.

If you are going to be storing your tumgreyspf database on an "ext2" or
"ext3" file-system, you have to be particularly careful about this
problem.

I have run a number of production e-mail servers using this with
extremely good results and absolutely no problems, however I do
acknowledge that there is a potential for problems.  Read the above URL
for more details on preventing these problems.

Over the last 18 months that it's been in use, and more than a year that
it's been publicly available, I've received many responses saying that
it worked great, and one blog post reporting the above problems.
tumgreyspf may not be for everyone, but many people do find it useful.

## QUICK-START INSTALL

There is a script called "tumgreyspf-install" provided with this
software.  I have had a report that it didn't work, so I would recommend
against running it, instead see the "INSTALL INSTRUCTIONS" section at
the end of this document for manual installation instructions.  The
install process is fairly easy, requiring some simple changes to the
Postfix configuration files.

## LOGGING

tumgreyspf will log messages to syslog about it's activities.  The
"debugLevel" value in "tumgreyspf.conf" can be increased to get
additional information to be logged.  When set to a value of "0", only
test results (greylist/SPF hits/misses) are logged.  Look for
"tumgreyspf" in your mail log files.

## TESTING

The best way to test tumgreyspf is to simulate SMTP connections, then
watch the logs and look in the ".../data/" directory for greylist
settings.  This testing probably needs to be done from a remote system.

For example, suppose we have a machine "10.9.8.7" that we want to run
tests against our mail server "10.1.2.3":

      Log into 10.9.8.7.
      Run "telnet 10.1.2.3 25"
      Type "helo example.com"
      Type "mail from: <user1@example.com>"
      Type "rcpt to: <user2@example.com>"

Note that "user2@example.com" needs to be a valid local e-mail address
in most cases, and that "user1@example.com" is subject to SPF blocking.
The first time you do this, you should receive the response:

      450 <user2@example.com>: Recipient address rejected: Service
      unavailable, greylisted.

   This indicates that the greylisting is working.

   Check the logs, you should see something similar to:

      Aug 22 19:52:49 mail tumgreyspf[12182]: Initial greylisting:
         REMOTEIP="10.9.8.7" HELO="example.com"
         SENDER="user1@example.com" RECIPIENT="user2@example.com" QUEUEID=""
      Aug 22 19:52:49 mail databytes[12184]: RCPT_INFO:
         REMOTEIP="10.9.8.7" HELO="example.com"
         SENDER="user1@example.com" RECIPIENT="user2@example.com" QUEUEID=""
      Aug 22 19:52:49 mail postfix/smtpd[11992]: NOQUEUE: reject: RCPT
         from testhost.example.com[10.9.8.7]: 450
         <user2@example.com>: Recipient address rejected: Service unavailable,
         greylisted.; from=<user1@example.com> to=<user2@example.com>
         proto=SMTP helo=<example.com>

   The "Initial greylisting" indicates that the record was not found in the
   database, and that a new entry was created.

   Now look in the greylist data for this entry:

      ls /path/to/data/client_address/10/9/8/7/greylist/user1@example.com/user2@example.com

   Wait 10 minutes (or whatever you set the greylisting time to) and try
   it again.  This time, in response to your "rcpt to" line, you should
   get:

      250 Ok

   or (if you have enabled SPF blocking for your domain):

      554 <user2@example.com>: Recipient address rejected: Please see
      http://spf.pobox.com/why.html?sender=user2%40example.com&ip=10.9.8.7&receiver=spfquery

   The only way to get around the SPF block is to either disable SPF
   checking in tumgreyspf (perhaps for this IP only, see the
   "CONFIGURATION" section below), or change your SPF configuration so that
   it allows mail from your test machine.

## CONFIGURATION

   **NOTE:** After changing "tumgreyspf.conf", you should run
   "tumgreyspf-configtest" to ensure that it's correct.  This only applies
   to changes made to the "tumgreyspf.conf" master configuration file.

   Configurations are processed from the top down, in the order specified
   by "OTHERCONFIGS".  So, settings in a top-level \_\_default\_\_ file will be
   overridden if set in a configuration below that top level.

   There is the \_\_default\_\_ file at the top level that is used as a
   default for all decisions. If you wish to disable SPF or greylist for
   a specific IP/subnet/sender/recipient, you simply make a \_\_default\_\_
   file in a subdirectory under config matching the entity you wish to
   match, with SPF or other checks disabled.

   For example, if you want to disable SPF queries for hosts in 192.168.10.0/24:

      mkdir /var/spool/tumgreyspf/config/client_address/192/168/10/
      edit /var/spool/tumgreyspf/config/client_address/192/168/10/__default__

   The \_\_default\_\_ file should contain:

      SPFSEEDONLY=0
      GREYLISTTIME=300
      CHECKERS=
      OTHERCONFIGS=

   Note that for a specific IP address, the last component is a file,
   having the same structure as the \_\_default\_\_.  For example, to block the
   address "10.1.2.3", you would create a file named "3" under the
   directory ".../config/client_address/10/1/2".

   The above sets CHECKERS and OTHERCONFIGS to nothing, so for that subnet
   no checks are done.  All other IP address blocks are still using the top
   level \_\_default\_\_

   CONFIGURATION VALUES

      SPFSEEDONLY=1 will only check SPF, not use it for decisions.

      GREYLISTTIME is the number of seconds to wait before allowing a
      an incoming message.  Unless you have a good reason for it, this
      should never be more than 3 hours or it may cause warnings about
      undeliverable e-mail to be sent.

      CHECKERS is one of the set of 'spf' and 'greylist'.  This is a list
      of checks to perform.  Note that they are done in the listed order.

      OTHERCONFIGS specifies which configurations will be used.  Note that
      these configurations are read a maximum of once, and are applied in
      order.  If another configuration changes this list, any
      configurations that are already done will be skipped.  Allowed values
      are:

         client_address

            Look for configuration values based on the remote IP address.
            For example, if the remote host "10.9.8.7" is connecting,
            the following will be tried:

               .../config/client_address/10/__default__
               .../config/client_address/10/9/__default__
               .../config/client_address/10/9/8/__default__
               .../config/client_address/10/9/8/7

         envelope_sender

            Split the envelope sender (not the header "From" address) into
            "domain" and "local" parts, and look for a domain-specific
            configuration, or a configuration specific to a particular
            sender.  So, if "user@example.com" sends a message, the
            following files would be tried:

               .../config/envelope_sender/example.com/__default__
               .../config/envelope_sender/example.com/user

            Note that special characters other than @, _ (underscore), -
            (dash), . (dot), and + (plus) are escaped using "%DD" format,
            where "DD" is the hex value of the ASCII character.  Also note
            that a leading "." in a domain or user is converted to "%2e",
            to prevent the confusion of "hidden files".

         envelope_recipient

            This is handled the same as envelope_sender, but is the
            envelope recipient.  Note that this is not the value of the
            "To" header in the message, but the value in the envelope.

      GREYLISTEXPIREDAYS is a floating point number of days since receiving
      the last piece of e-mail after which a greylist entry will be
      expired.  This value is used by "tumgreyspf-clean".

INSTALL INSTRUCTIONS

   The fastest way to install tumgreyspf is to use the package for your
   system.  This will use "tumgreyspf-install" to attempt to automatically
   configure postfix for tumgreyspf.  However, it's recommended that you
   carefully review the Postfix configuration changes and verify that they
   are as you expect.

   INSTALLING THE SOFTWARE

      This does not need to be done if you've installed the RPM/Debian
      package.

      tumgreyspf uses two directories.  One is for the main tumgreyspf
      code, and the other is for it's data/configuration.  I call these
      directories "$TGSPROG" and "$TGSDATA" in the instructions below.
      Additionally, the user which tumgreyspf runs as is "$TGSUSER".

      Run the following commands:

         TGSPROG=/usr/local/lib/tumgreyspf
         TGSDATA=/var/local/lib/tumgreyspf
         TGSUSER=nobody

         #  set up directories
         mkdir -p "$TGSPROG" "$TGSDATA"/config
         mkdir "$TGSDATA"/data
         chown -R nobody "$TGSDATA"/data
         cp __default__.dist "$TGSDATA"/config/__default__

         #  install programs
         cp tumgreyspf tumgreyspf-clean tumgreyspf-configtest "$TGSPROG"
         cp tumgreyspf-install tumgreyspf-stat tumgreyspfsupp.py "$TGSPROG"
         cp tumgreyspf.conf "$TGSDATA"/config/

         #  change permissions and ownership
         chown -R "$TGSUSER" "$TGSDATA"
         chown -R root "$TGSPROG" "$TGSDATA"/config
         chmod 700 "$TGSDATA"/data
         chmod -R 755 "$TGSDATA"/config

      If you have changed the values of TGSPROG or TGSDATA, you will need
      to change the the paths in the following files.  In the .conf file,
      you will need to review the whole file, the other files have the
      required changes isolated to the top of the file:

         "$TGSDATA"/config/tumgreyspf.conf
         "$TGSPROG"/tumgreyspfsupp.py
         "$TGSPROG"/tumgreyspf
         "$TGSPROG"/tumgreyspf-clean
         "$TGSPROG"/tumgreyspf-stat

   CRONTAB

      WARNING: Make *SURE* you do this step, as not cleaning out the
      database may result in resource exhaustion in your file-system.

      Next, you will need to add a cron job which runs daily to clean out
      the the expired SPF entries.  On many systems, there is a
      "/etc/cron.d" directory, and the following can be be used to add an
      entry:

         echo 0 0 * * * $TGSUSER $TGSPROG/tumgreyspf-clean \
               >/etc/cron.d/tumgreyspf

      Otherwise, you will need to use "crontab -e -u $TGSUSER" to add the
      following entry:

         0 0 * * * $TGSPROG/tumgreyspf-clean

      Note that you cannot use the literal "$TGSPROG", you will have to
      replace it with whatever the real value is.

   CONFIGURING POSTFIX

      WARNING: In these examples, you cannot use the literal "$TGS"
      variables.  You will have to manually replace the appropriate values,
      they are simply there to mark where the changes need to be.

      Add to your postfix master.cf:

         tumgreyspf  unix  -       n       n       -       -       spawn
            user=nobody argv=$TGSPROG/tumgreyspf

      Next, main.cf must be configured so that "smtpd_recipient_restrictions"
      includes a call to the tumgreyspf policy filter.  If you already have
      a "smtpd_recipient_restrictions" line(s), you can add the following line
      anywhere after the line which reads "reject_unauth_destination".

         check_policy_service unix:private/tumgreyspf

      WARNING: It's very important that you have
      "reject_unauth_destination" before the "check_policy_service".  If
      you do not, your system may be an open relay.

      So, for example, a minimal "smtpd_recipient_restrictions" may look like:

         smtpd_recipient_restrictions = \
            reject_unauth_destination, \
            check_policy_service unix:private/tumgreyspf

      Please consult the postfix documentation for more information on
      these and other settings you may wish to have in the
      "smtpd_recipient_restrictions" configuration.

      You will also need to have a line in the main.cf which reads:

         tumgreyspf_time_limit = 3600

   SPF INSTALLATION

      NOTE: SPF is optional, but it's use, particularly it's use before
      greylisting, will help reduce spam and will reduce the size of the
      greylist database.  This may prevent or lessen the problems mentioned
      in the "NOTE BEFORE YOU USE TUMGREYSPF" section.

      tumgreyspf can also use an external SPF program to do SPF lookups.
      You can use any of the following:

         Download libspf2 from http://www.libspf2.org/ untar and run
         "./configure; make", then copy "src/spfquery/spfquery_static" to
         "$TGSPROG".

         The Mail::SPF::Query Perl module includes a "spfquery" package
         that tumgreyspf can be used with.  Once installed, change your
         tumgreyspf.conf file to list the path to "spfquery".
         Information on downloading this package is available
         from http://spf.pobox.com/downloads.html

         The Python pyspf package from http://www.wayforward.net/spf/ can
         also be used.  If this is installed, tumgreyspf will automatically
         use it.

## COMMON PROBLEMS

   SPF checks need to be bypassed for relays for the domain, such as
   secondary MX servers.  Putting an mx entry in your SPF TXT record is
   not sufficient to do this, as that only covers your *OUTGOING* e-mail.
   Incoming e-mail is controlled by the senders SPF record, which probably
   doesn't list your secondary MX hosts.  :-)

   One way of bypassing this check would be to ensure that MX servers are
   listed in mynetworks, and that permit_mynetworks is ahead of the call to
   tumgreyspf.
