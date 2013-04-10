#
# Regular cron jobs for the opensrf package
#
0 4	* * *	root	[ -x /usr/bin/opensrf_maintenance ] && /usr/bin/opensrf_maintenance
