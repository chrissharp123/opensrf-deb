#!/bin/bash
#TODO: properly attribute the original authors of this file
#TODO: add a 'status' command
#TODO: create an upstart job instead?

### BEGIN INIT INFO
# Provides:          opensrf
# Required-Start:    $local_fs $remote_fs $network $syslog
# Required-Stop:     $local_fs $remote_fs $network $syslog 
# Default-Start:     2 3 4 5
# Default-Stop:      0 1 6
# X-Interactive:     true
# Short-Description: Start/stop OpenSRF Services
### END INIT INFO
. /lib/lsb/init-functions

OPENILS_BASE="/openils"
OPENILS_CORE="${OPENILS_BASE}/conf/opensrf_core.xml"
SRU_LOG="${OPENILS_BASE}/var/log/sru.log"

PIDFILES="${OPENILS_BASE}/var/run"
SIP_CONF="${OPENILS_BASE}/conf/oils_sip.xml"

REP_LOCK="${OPENILS_BASE}/var/lock/reporter-LOCK"
REP_NAME="Clark Kent, waiting for trouble"

sru_name='simple2zoom'

export PATH=$PATH:${OPENILS_BASE}/bin

if [ $(whoami) != 'opensrf' ]; then
 PERL5LIB='/openils/lib/perl5:$PERL5LIB';
fi;

start_opensrf() {
        sleep 3
	log_daemon_msg "Starting Evergreen OpenSRF:"
	su - opensrf -c /bin/bash -c "PERL5LIB=${PERL5LIB}:${OPENILS_BASE}/lib/perl5 PATH=${PATH}:${OPENILS_BASE}/bin osrf_ctl.sh  -a start_all"
	if [ ! -e ${OPENILS_BASE}/var/web/eg_cache_hash ]
		then
			log_daemon_msg "Running Autogen...:"
			su - opensrf /bin/bash -c "PERL5LIB=${PERL5LIB}:${OPENILS_BASE}/lib/perl5 PATH=${PATH}:${OPENILS_BASE}/bin autogen.sh -u"
	fi
}

stop_opensrf() {
	log_daemon_msg "Stopping Evergreen OpenSRF:"
	su - opensrf -c /bin/bash -c "PERL5LIB=${PERL5LIB}:${OPENILS_BASE}/lib/perl5 PATH=${PATH}:${OPENILS_BASE}/bin osrf_ctl.sh  -a stop_all"
	sleep 3
	rm -f $PIDFILES/*.pid
}

autogen() {
        echo "Running Autogen Update"
        su - opensrf /bin/bash -c "PERL5LIB=${PERL5LIB}:${OPENILS_BASE}/lib/perl5 PATH=${PATH}:${OPENILS_BASE}/bin autogen.sh -u"
}


case "$1" in
    start)
        start_opensrf
	/etc/init.d/apache2 restart
    ;;
    stop)
        stop_opensrf
    ;;
    restart)
	/etc/init.d/apache2 stop
	log_daemon_msg "Restarting Evergreen OpenSRF:"
        stop_opensrf
	sleep 2
        start_opensrf
	/etc/init.d/apache2 start
    ;;
    autogen)
        autogen
    ;;
*)
        echo " * Usage: /etc/init.d/eg_opensrf {start|stop|restart|autogen}"
        exit 1
    ;;
esac;
