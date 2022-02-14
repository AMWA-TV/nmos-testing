#!/bin/bash

# Start NMOS Testing
python3 nmos-test.py &
  
# Start Testing Facade
python3 nmos-testing-facade.py &
  
# Wait for any process to exit
wait -n
  
# Exit with status of process that exited first
exit $?