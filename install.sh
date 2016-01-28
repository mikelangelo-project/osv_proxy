#!/bin/bash

# Install required system and python packages.
# For system packages, sudo rights are required.

# osv_proxy.sh assumes virtualenv named osv_proxy at location $HOME/.virtualenvs/osv_proxy
VEPATH="$HOME/.virtualenvs"
VENAME="$HOME/.virtualenvs/osv_proxy"

SRCDIR=`dirname "$0"`
SRCDIR=`realpath "$SRCDIR"`

# options
OPT_DRY=0
OPT_YES=0

function print_help() {
    cat <<EOF 1>&2
Usage: $0 [option]
Options:
  -n|--dry-run       only show commands to be run
  -y|--yes           assume yes answer for apt-get install
EOF
}

# parse options
while [[ $# > 0 ]]
do
key="$1"
case $key in
    -h|--help)
    print_help
    exit 0
    ;;
    -n|--dry-run)
    OPT_DRY=1
    ;;
    -y|--yes)
    OPT_YES=1
    ;;
    *)
    echo "ERROR unknown option: $key"
    print_help
    exit 1
    ;;
esac
shift # past argument or value
done
#
CMDPREFIX=""
if [ "$OPT_DRY" == "1" ]; then
    CMDPREFIX="echo"
fi
#
APT_OPT=""
if [ "$OPT_YES" == "1" ]; then
    APT_OPT="-y"
fi

function os_package_install() {
    pkgname=$1
    test -z "`dpkg --get-selections | grep '^'$pkgname'[[:space:]]*install$'`"
    installed=$?  # print 1 if installed, 0 if not
    if [ "0" == "$installed" ]; then
        $CMDPREFIX sudo apt-get $APT_OPT install $pkgname
    fi
}

# OS level requirements
os_package_install python-pip
os_package_install python-dev
os_package_install libvirt-bin
os_package_install libvirt-dev

# user should be member of libvirt and kvm group.
if [ -z "`cat /etc/group | grep '^libvirtd:' | sed 's/[:,]/ /g' | grep -w $USER`" ] || \
   [ -z "`cat /etc/group | grep '^kvm:' | sed 's/[:,]/ /g' | grep -w $USER`" ]; then
    $CMDPREFIX sudo usermod -a -G libvirtd,kvm $USER
fi

# system-wide or user-wide virtualenv is ok
if [ -z "`which virtualenv`" ]; then
    $CMDPREFIX pip install virtualenv
fi

# make virtualenv, install requirements
if [ ! -d "$VEPATH" ]; then
    $CMDPREFIX mkdir "$VEPATH"
fi
if [ ! -d "$VENAME" ]; then
    $CMDPREFIX virtualenv "$VENAME"
fi
$CMDPREFIX source "$VENAME/bin/activate"
$CMDPREFIX pip install -r "$SRCDIR/requirements-run.txt"

