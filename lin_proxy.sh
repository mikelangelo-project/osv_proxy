#!/bin/bash

source $HOME/.virtualenvs/osv_proxy/bin/activate
PYNAME=`echo $0 | sed 's/.sh$/.py/'`
exec $PYNAME $@
