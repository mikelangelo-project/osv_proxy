#!/bin/bash

source $HOME/.virtualenvs/osv_proxy/bin/activate
PYNAME=`echo $0 | sed 's/.sh$/.py/'`
# Make sure that mpirun MPI_ARGS --launch-proxy "proxy.sh aa bb" starts our proxy as
# proxy.sh aa bb MPI_ARGS --launch-proxy "proxy.sh aa bb"
exec $PYNAME "$@"
