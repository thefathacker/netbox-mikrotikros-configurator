import json
import threading
import types
import ipaddress
from librouteros import connect
from librouteros.query import Key

class Keys:
    id = Key(".id")
    rid = Key("id")
    name = Key("name")
    mac = Key("mac-address")
    comment = Key("comment")
    interface = Key("interface")
    interfaces = Key("interfaces")
    address = Key("address")
    inactive = Key("inactive")
    area = Key("area")
    type = Key("type")
    passive = Key("passive")

class ROSDevice(threading.Thread):
    def getNBTags(self):
        tags = types.SimpleNamespace()
        for tag in self.nb.extras.tags.all():
            if(tag.name == "ospf-ptp"): tags.ospf_ptp = tag
            if(tag.name == "ospf-passive"): tags.ospf_passive = tag
        return tags
    def generateComment(self, intf):
        desc = ""
        if(intf.cable is not None):
            desc = intf.connected_endpoint.device.name + " => " + intf.connected_endpoint.name
        if(desc != "" and intf.description != ""): desc = desc + " - " + intf.description
        elif(desc == "" and intf.description != ""): desc = intf.description
        return desc
    def reviewRouterID(self,api,api_ip):
        rid_found = False
        for rid in api.path("/routing/id"):
            if(rid["name"] != self.dev.name and "dynamic" not in rid): api.path("/routing/id").remove(rid[".id"])
            elif(rid["name"] == self.dev.name):
                rid_found = True
                if(rid["id"] != api_ip): api.path("/routing/id").update(**{".id":rid[".id"], "id":api_ip})
        if(not rid_found): api.path("/routing/id").add(name=self.dev.name, id=api_ip)
    def reviewOSPFInst(self,ver,api):
        ospfinst_found = False
        ospfinst_name = "ospf" + str(ver) + "-instance-" + self.dev.site.slug
        for ospfinst in api.path("/routing/ospf/instance"):
            if(ospfinst['name'] == ospfinst_name):
                ospfinst_found = True
                if(ospfinst['router-id'] != self.dev.name): api.path("/routing/ospf/instance").update(**{".id":ospfinst[".id"], "router-id":self.dev.name})
        if(not ospfinst_found): 
            ospfinstid = api.path("/routing/ospf/instance").add(name=ospfinst_name, version=ver)
            api.path("/routing/ospf/instance").update(**{".id":ospfinstid, "router-id":self.dev.name})
    def reviewOSPFArea(self,ver,api):
        ospfarea_found = False
        ospfarea_name = "ospf" + str(ver) + "-area-" + self.dev.site.slug
        ospfinst_name = "ospf" + str(ver) + "-instance-" + self.dev.site.slug
        for ip in self.nb.ipam.ip_addresses.filter(id=self.dev.primary_ip.id):
            ospfarea_id = ip.vrf.rd
        for ospfarea in api.path("/routing/ospf/area"):
            if(ospfarea['name'] == ospfarea_name):
                ospfarea_found = True
        if(not ospfarea_found):
            new_area_id = api.path("/routing/ospf/area").add(name=ospfarea_name, instance=ospfinst_name)
            api.path("/routing/ospf/area").update(**{".id":new_area_id, "area-id":ospfarea_id})
    def reviewOSPFInterface(self, nbi, api):
        ospf2area = "ospf2-area-" + self.dev.site.slug
        ospf3area = "ospf3-area-" + self.dev.site.slug
        ospf = False
        passive = False
        type = 'broadcast'
        exists = False
        if(self.tags.ospf_ptp in nbi.tags):
            type = 'ptp'
            ospf = True
        if(self.tags.ospf_passive in nbi.tags):
            passive = True
            ospf = True
        for area in [ospf2area, ospf3area]:
            for intf in api.path("/routing/ospf/interface-template").select(Keys.id, Keys.area, Keys.type, Keys.interfaces, Keys.passive).where(Keys.interfaces == nbi.name, Keys.area == area):
                exists = True
                if(not ospf): api.path("/routing/ospf/interface-template").remove(intf['.id'])
                if("passive" in intf and not passive): api.path("/routing/ospf/interface-template").update(**{'.id':intf['.id'], 'passive':False})
                if("passive" not in intf and passive): api.path("/routing/ospf/interface-template").update(**{'.id':intf['.id'], 'passive':True})
                if(intf['type'] != type): api.path("/routing/ospf/interface-template").update(**{'.id':intf['.id'], 'type':type})
            if(ospf and not exists):
                new_intft = api.path("/routing/ospf/interface-template").add(interfaces=nbi.name, area=area, type=type)
                if(passive): api.path("/routing/ospf/interface-template").update(**{'.id':new_intft, 'passive':True})
    def __init__(self, tid, dev, netbox):
        threading.Thread.__init__(self)
        self.threadID = tid
        self.name = dev.name
        self.dev = dev
        self.nb = netbox
        self.tags = self.getNBTags()
    def run(self):
        api_ip = self.dev.primary_ip.address.split("/")[0]
        api = connect(username="svc.netbox", password="Passw0rd", host=api_ip)

        self.reviewRouterID(api, api_ip)
        for ver in [2,3]:
            self.reviewOSPFInst(ver, api)
            self.reviewOSPFArea(ver, api)
        
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
            self.reviewOSPFInterface(nbi, api)
            