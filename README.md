In direcotry osv/:
A simple tool to run and configure OSv containers. Can set environment variables, before running application.
 
That code is used be orted proxy.

 * INSTALL
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
** Nested virtualization
 https://fedoraproject.org/wiki/How_to_enable_nested_virtualization_in_KVM
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
