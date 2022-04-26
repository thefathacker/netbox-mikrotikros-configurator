import json
import threading
import ipaddress
from librouteros import connect
from librouteros.query import Key

#{'value': 'virtual', 'display_name': 'Virtual'}
#{'value': 'bridge', 'display_name': 'Bridge'}
#{'value': 'lag', 'display_name': 'Link Aggregation Group (LAG)'}

        #for type in self.nb.dcim.interfaces.choices()['type']:
        #    print(type)
        #for intf in api.path("/interface/ethernet"):
        #    print(intf)

class Keys:
    id = Key(".id")
    name = Key("name")
    mac = Key("mac-address")
    comment = Key("comment")

class ROSDevice(threading.Thread):
    
    
    def __init__(self, tid, dev, netbox):
        threading.Thread.__init__(self)
        self.threadID = tid
        self.name = dev.name
        self.dev = dev
        self.nb = netbox
    def run(self):
        ip = self.dev.primary_ip.address.split("/")[0]
        print(ip)
        api = connect(username="svc.netbox", password="Passw0rd", host=ip)

        for nbi in self.nb.dcim.interfaces.filter(device=self.dev):
            int_exists = 0
            for rbi in api.path("/interface").select(Keys.id, Keys.name, Keys.mac, Keys.comment).where(Keys.mac == nbi["mac_address"]):
                int_exists = int_exists + 1
            if(not int_exists):
                print("Interface Doesn't Exist")
            for rbi in api.path("/interface").select(Keys.id, Keys.name, Keys.mac, Keys.comment).where(Keys.mac == nbi["mac_address"]):
                #print(rbi)
                if("comment" not in rbi):
                    if(nbi["description"] != ""): api.path("/interface").update(**{".id":rbi[".id"], "comment":nbi["description"]})
                else:
                    if(nbi["description"] != rbi["comment"]): api.path("/interface").update(**{".id":rbi[".id"], "comment":nbi["description"]})