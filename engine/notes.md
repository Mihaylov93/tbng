chmod +s nmcli

 sudo apt-get install obfsproxy obfs4proxy

UseBridges 1  
Bridge obfs3 YOUR_BRIDGE 
ClientTransportPlugin obfs3 exec /usr/bin/obfsproxy --managed

UseBridges 1
Bridge obfs4 YOUR_BRIDGE
ClientTransportPlugin obfs4 exec /usr/bin/obfs4proxy

https://gist.github.com/Apsu/5021255

https://stackoverflow.com/questions/24196932/how-can-i-get-the-ip-address-of-eth0-in-python

ip link set wlanxx down
