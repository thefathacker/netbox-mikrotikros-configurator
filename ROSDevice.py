import json
import threading
import types
import ipaddress
from ROS.Keys import Keys
from librouteros import connect

class ROSDevice(threading.Thread):
    def generateInterfaceComment(self, intf):
        desc = ""
        if(intf.cable is not None):
            desc = intf.connected_endpoint.device.name + " => " + intf.connected_endpoint.name
        if(desc != "" and intf.description != ""): desc = desc + " - " + intf.description
        elif(desc == "" and intf.description != ""): desc = intf.description
        return desc
    def getNBTags(self):
        tags = types.SimpleNamespace()
        for tag in self.nb.extras.tags.all():
            if(tag.name == "ospf-ptp"): tags.ospf_ptp = tag
            if(tag.name == "ospf-passive"): tags.ospf_passive = tag
        return tags
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
        self.dev = dev
        self.nb = netbox
        self.tags = self.getNBTags()
    def run(self):
        api_ip = self.dev.primary_ip4.address.split("/")[0]
        api = connect(username="svc.netbox", password="Passw0rd", host=api_ip)
        
        # Write Bridges to Device
        for nbi in self.nb.dcim.interfaces.filter(device=self.dev, type="bridge"):
            exists = False
            comment = self.generateInterfaceComment(nbi)
            for rbi in api.path("/interface/bridge").select(Keys.id, Keys.name, Keys.mac, Keys.comment).where(Keys.name == nbi.name):
                if(rbi["mac-address"] != nbi.mac_address):
                    nbi.mac_address = rbi["mac-address"]
                    nbi.save()
                if(comment in rbi):
                    if(rbi["comment"] != comment): api.path("/interface").update(**{".id":rbi[".id"], "comment":comment})
                else:
                    if(comment != ""): api.path("/interface").update(**{".id":rbi[".id"], "comment":comment})
                exists = True
            if(not exists):
                nid = api.path("/interface/bridge").add(**{"name":nbi.name, "comment":comment})
                for trbi in api.path("/interface/bridge").select(Keys.id, Keys.name, Keys.mac, Keys.comment).where(Keys.id == nid):
                    nbi.mac_address = trbi["mac-address"]
                    nbi.save()
        # Review Bridges on Device
        for rbi in api.path("/interface/bridge").select(Keys.id, Keys.name, Keys.mac, Keys.comment):
            exists = False
            for nbi in self.nb.dcim.interfaces.filter(device=self.dev, type="bridge", name=rbi["name"]):
                if(nbi.name == rbi["name"]): exists = True
            if(not exists): api.path("/interface/bridge").remove(rbi[".id"])
        # Write LAGs to Device
        for nbi in self.nb.dcim.interfaces.filter(device=self.dev, type="lag"):
            print("NEED TO SETUP LAGG") #SETUP LATER
        # Review Ethernet Interfaces
        for nbi in self.nb.dcim.interfaces.filter(device=self.dev):
            if(nbi.type.value not in ["virtual","bridge","lag"]):
                comment = self.generateInterfaceComment(nbi)
                for rbi in api.path("/interface/ethernet").select(Keys.id, Keys.name, Keys.mac, Keys.comment).where(Keys.mac == nbi.mac_address):
                    if("comment" not in rbi):
                        if(comment != ""): api.path("/interface/ethernet").update(**{".id":rbi[".id"], "comment":comment})
                    else:
                        if(comment != rbi["comment"]): api.path("/interface/ethernet").update(**{".id":rbi[".id"], "comment":comment})
                    if(nbi.name != rbi["name"]): api.path("/interface/ethernet").update(**{".id":rbi[".id"], "name":nbi.name})
                #print() #SETUP LATER
        
        # Write FHRP
        for nbi in self.nb.dcim.interfaces.filter(device=self.dev):
            vrrp4_exists = False
            vrrp6_exists = False
            for rbi in api.path("/interface/vrrp").select(Keys.id, Keys.name, Keys.mac, Keys.comment).where(Keys.name == (nbi.name + ".vrrp4")):
                vrrp4_exists = True
            for rbi in api.path("/interface/vrrp").select(Keys.id, Keys.name, Keys.mac, Keys.comment).where(Keys.name == (nbi.name + ".vrrp6")):
                vrrp6_exists = True
            ##### NEED TO WORK OUT HOW TO QUERY PRIORITY
            if(nbi.count_fhrp_groups):
                if(not vrrp4_exists):
                    api.path("/interface/vrrp").add(**{"name":(nbi.name + ".vrrp4"), "vrid":4, "interface":nbi.name, "version":3, "v3-protocol":"ipv4"})
                if(not vrrp6_exists):
                    api.path("/interface/vrrp").add(**{"name":(nbi.name + ".vrrp6"), "vrid":6, "interface":nbi.name, "version":3, "v3-protocol":"ipv6"})
            else:
                if(vrrp4_exists):
                    for rbi in api.path("/interface/vrrp").select(Keys.id, Keys.name, Keys.mac, Keys.comment).where(Keys.name == (nbi.name + ".vrrp4")):
                        api.path("/interface/vrrp").remove(rbi[".id"])
                if(vrrp6_exists):
                    for rbi in api.path("/interface/vrrp").select(Keys.id, Keys.name, Keys.mac, Keys.comment).where(Keys.name == (nbi.name + ".vrrp6")):
                        api.path("/interface/vrrp").remove(rbi[".id"])
        
        # Write VLANs to Device
        for nbi in self.nb.dcim.interfaces.filter(device=self.dev, type="virtual"):
            exists = False
            vid = 0
            if(nbi.untagged_vlan is not None):
                vid = nbi.untagged_vlan.vid
            if(nbi.parent is not None):
                if(nbi.mac_address != nbi.parent.mac_address):
                    nbi.mac_address = nbi.parent.mac_address
                    nbi.save()
                for rbi in api.path("/interface/vlan").select(Keys.id, Keys.name, Keys.mac, Keys.comment, Keys.vid).where(Keys.mac == nbi.mac_address, Keys.name == nbi.name):
                    exists = True
                    if(rbi["vlan-id"] != vid and vid): api.path("/interface/vlan").update(**{".id":rbi[".id"], "vlan-id":vid})
            if(not exists and vid and nbi.parent is not None):
                api.path("/interface/vlan").add(**{"name":nbi.name, "interface":nbi.parent.name, "vlan-id":vid})
        # Review VLANs on Device
        for rbi in api.path("/interface/vlan").select(Keys.id, Keys.name, Keys.mac, Keys.comment, Keys.vid):
            exists = False
            for nbi in self.nb.dcim.interfaces.filter(device=self.dev, type="virtual", name=rbi["name"]):
                if(nbi.name == rbi["name"]): exists = True
            if(not exists): api.path("/interface/vlan").remove(rbi[".id"])
        # IP Configuration
        for nbi in self.nb.dcim.interfaces.filter(device=self.dev):
            for ip in self.nb.ipam.ip_addresses.filter(device=self.dev):
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
        # OSPF Configuration
        self.reviewRouterID(api, api_ip)
        for ver in [2,3]:
            self.reviewOSPFInst(ver, api)
            self.reviewOSPFArea(ver, api)
        for nbi in self.nb.dcim.interfaces.filter(device=self.dev):
            self.reviewOSPFInterface(nbi, api)