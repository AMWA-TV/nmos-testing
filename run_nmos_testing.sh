#!/bin/bash

# Start Avahi Daemon for mDNS discovery
[ -e "/etc/init.d/dbus" ] && /etc/init.d/dbus start || dbus-daemon --system --fork
[ -e "/etc/init.d/avahi-daemon" ] && /etc/init.d/avahi-daemon start || avahi-daemon --daemonize

# Start NMOS Testing
python3 nmos-test.py &
  
# Start Testing Facade
python3 nmos-testing-facade.py &
  
# Wait for any process to exit
wait -n
  
# Exit with status of process that exited first
exit $?
