import json
import threading
import ipaddress
from librouteros import connect
from librouteros.query import Key

class Keys:
    id = Key(".id")
    name = Key("name")
    mac = Key("mac-address")
    comment = Key("comment")
    interface = Key("interface")
    address = Key("address")

class ROSDevice(threading.Thread):
    def generateComment(self, intf):
        desc = ""
        if(intf.cable is not None):
            desc = intf.connected_endpoint.device.name + " => " + intf.connected_endpoint.name
        if(desc != "" and intf.description != ""): desc = desc + " - " + intf.description
        elif(desc == "" and intf.description != ""): desc = intf.description
        return desc

    def __init__(self, tid, dev, netbox):
        threading.Thread.__init__(self)
        self.threadID = tid
        self.name = dev.name
        self.dev = dev
        self.nb = netbox
    def run(self):
        api_ip = self.dev.primary_ip.address.split("/")[0]
        api = connect(username="svc.netbox", password="Passw0rd", host=api_ip)

        for nbi in self.nb.dcim.interfaces.filter(device=self.dev):
            int_exists = 0
            comment = self.generateComment(nbi)
            for rbi in api.path("/interface").select(Keys.id, Keys.name, Keys.mac, Keys.comment).where(Keys.mac == nbi["mac_address"]):
                int_exists = int_exists + 1
            if(not int_exists):
                if(nbi["type"]["value"] in ["virtual", "bridge", "lag"]):
                    api.path("/interface/bridge").add(**{"name":nbi["name"], "comment":comment})
                    for rbi in api.path("/interface/bridge").select(Keys.id, Keys.name, Keys.mac, Keys.comment).where(Keys.name == nbi["name"]):
                        nbi.mac_address = rbi["mac-address"]
                        nbi.save()
            for rbi in api.path("/interface").select(Keys.id, Keys.name, Keys.mac, Keys.comment).where(Keys.mac == nbi["mac_address"]):
                if("comment" not in rbi):
                    if(comment != ""): api.path("/interface").update(**{".id":rbi[".id"], "comment":comment})
                else:
                    if(comment != rbi["comment"]): api.path("/interface").update(**{".id":rbi[".id"], "comment":comment})
                if(nbi.name != rbi["name"]): api.path("/interface").update(**{".id":rbi[".id"], "name":nbi.name})
            for ip in self.nb.ipam.ip_addresses.filter(device=self.dev, assigned_object_type="dcim.interface"):
                if(ip.assigned_object_id != nbi.id): continue
                if(ip.family.value == 4):
                    count = 0
                    for rip in api.path("/ip/address").select(Keys.id, Keys.address, Keys.interface).where(Keys.address == ip.address):
                        if(rip['interface'] != nbi.name): api.path("/ip/address").update(**{".id":rip[".id"], "interface":nbi.name})
                        count = count + 1
                    if(not count): api.path("/ip/address").add(interface=nbi.name, address=ip.address)
                if(ip.family.value == 6):
                    count = 0
                    for rip in api.path("/ipv6/address").select(Keys.id, Keys.address, Keys.interface).where(Keys.address == ip.address):
                        if(rip['interface'] != nbi.name): api.path("/ipv6/address").update(**{".id":rip[".id"], "interface":nbi.name})
                        count = count + 1
                    if(not count): api.path("/ipv6/address").add(interface=nbi.name, address=ip.address)
            for rip in api.path("/ip/address").select(Keys.id, Keys.address, Keys.interface).where(Keys.interface == nbi.name):
                if(not len(self.nb.ipam.ip_addresses.filter(device=self.dev, address=rip["address"]))):
                    api.path("/ip/address").remove(rip[".id"])
            for rip in api.path("/ipv6/address").select(Keys.id, Keys.address, Keys.interface).where(Keys.interface == nbi.name):
                if(not len(self.nb.ipam.ip_addresses.filter(device=self.dev, address=rip["address"]))):
                    if("fe80::" not in rip["address"]): api.path("/ipv6/address").remove(rip[".id"])