In directory osv/:
A simple tool to run and configure OSv VMs. Can set environment variables, before running application.

That code is used be orted proxy.

# INSTALL

## with script

Run install.sh as user, which is supposed to run osv_proxy.py.
If some system packages are missing, ```sudo apt-get install``` will be invoked,
and the user will need to have sudo rights.

```
./install.sh --dry-run
./install.sh
```

Edit `conf/local_settings.py` to set OSV_SRC to path with OSv source code.

## manually

Prepare virtualenv (ubuntu 14.04.3):
```
sudo apt-get install libvirt-bin qemu-kvm
sudo apt-get install python-dev python-pip
sudo pip install virtualenv
sudo pip install virtualenvwrapper

cat <<EOF >> ~/.bashrc

export WORKON_HOME=~/.virtualenvs
source /usr/local/bin/virtualenvwrapper.sh

EOF
```

Install inside virutalenv:
```
mkvirtualenv osv_proxy
workon osv_proxy
sudo apt-get install python-dev libvirt-dev
pip install -r requirements-run.txt
```

User running lin_proxy.sh should be member of libvirt and kvm group:
```
usermod -a -G libvirtd,kvm SOMEONE
```

Edit `conf/local_settings.py` to set OSV_SRC to path with OSv source code.

## Nested virtualization

 * https://fedoraproject.org/wiki/How_to_enable_nested_virtualization_in_KVM

In case you are testing inside VM, and are spinning up new VMs in a VM, you should enable nested virtualization.

On host, check:
```
cat /sys/module/kvm_intel/parameters/nested
Y

# If not:
sudo rmmod kvm-intel
sudo sh -c "echo 'options kvm-intel nested=y' >> /etc/modprobe.d/dist.conf"
sudo modprobe kvm-intel
```

For VM, set:
```
<cpu mode='host-passthrough'>...</cpu>

# And check after shutdown/reboot:
ls -la /dev/kvm
```

## Install mpirun compatible with OSv VM orted.so

The mpirun has to be "compatible" with the version of OpenMPI inside OSv VM.
Compatible means same OpenMPI version and same OpenMPI compile-time configuration (OpenMPI ./configure flags).
Otherwise, mpirun might send to orted.so unknown parameters, causing orted.so to fail running.

If you built OSv image with OSv build script, and used mike-apps repository for OpenMPI,
then compatible mpirun can be installed from mike-apps. Because OpenMPI was configured with 
```prefix=$HOME/openmpi-bin```, the install step will not replace existing system-wide OpenMPI binaries.
For the same reason, you should manually configure your PATH and LD_LIBRARY_PATH to actually use this binaries.

```
cd osv
scripts/build mode=debug image==OpenMPI,openmpi-hello,cli -j5

cd mike-apps/OpenMPI/ompi-release/build-osv/
sudo make install

cat <<EOF >> ~/.bashrc
# MAGIC LINE mike-apps OpenMPI included : OSv mike-apps openmpi bin/libs 
export PATH=$HOME/openmpi-bin/bin:\$PATH
export LD_LIBRARY_PATH=$HOME/openmpi-bin/lib:\$LD_LIBRARY_PATH
EOF

source ~/.bashrc
which mpirun
```

# USAGE

osv_proxy is used together with OpenMPI mpirun to start MPI program inside OSv VMs.

You have to edit conf/local_settings.py file to set where is OSv source code located.
```
# conf/local_settings.py
OSV_SRC = '/home/justin_cinkelj/devel/mikelangelo/osv'
```

An example to run mpi_hello (for OSv compiled to shared object file named mpi_hello.so) is:
```
mpirun -H user@host -n 2 --launch-agent /host/path/to/lin_proxy.sh /vm/path/to/mpi_hello.so
```

The ```/host/path/to/lin_proxy.sh``` is inside host filesystem. The lin_proxy.sh binary has to be at same path on all hosts.
The ```/vm/path/to/mpi_hello.so``` is inside VM image filesystem.

Not that mpirun uses --launch-agent for remote hosts only. For localhost it seems to be simply ignored, so you cannot run MPI program on localhost.

Debug informations are written to "/tmp/orted_lin_proxy.log" file, on each host used by mpirun.