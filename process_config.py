
from ciscoconfparse import CiscoConfParse
from netutils.interface import abbreviated_interface_name
from pathlib import Path
import pprint
from loguru import logger


class analize_cisco_running_config():

    def __init__(self,folder):
        logger.remove()
        self.files = {}
        folder_path = Path(folder)
        # Loops only through text files in this folder
        for file in folder_path.glob("*.ios"):
            parse = CiscoConfParse(f"{folder}/{file.name}",debug=0, factory=True)
            self.files[file.name] = parse


    def find_curr_config_stuff(self,mgm_vlan):
        vlan_info = {}
        for switch in self.files:
            hostname  = self.files[switch].find_objects(r"^hostname")
            text_hostname = hostname[0].text.split()[-1]
            mgminter = self.files[switch].find_objects(fr"^interface Vlan{mgm_vlan}")
            ip_address = "" 
            for child in mgminter[0].children:
                if "ip address" in child.text:
                    ip_address = child.text.strip().split(" ")[2]
            standard_name  = f"{text_hostname}\n{ip_address}"
            monitor = self.files[switch].find_objects(r"^monitor session")
            vlan_info[standard_name] = {}
            vlan_info[standard_name]["monitor"] = []
            for mon in monitor:
                vlan_info[standard_name]["monitor"].append(mon.text)
            vlans = self.files[switch].find_objects(r"^vlan \d+")
            vlan_info[standard_name]["vlans"] = {}
            for vlan in vlans:
                vlan_info[standard_name]["vlans"][vlan.text] = []
                for child in vlan.children:
                    vlan_info[standard_name]["vlans"][vlan.text].append(child.text)
            interfaces = self.files[switch].find_objects(r"^interface")
            trunkInterfaces = {}
            for face in interfaces:
                save_face = False
                total_text = []
                for child in face.children:
                    total_text.append(child.text)
                    if "mode trunk" in child.text:
                        save_face = True
                if save_face:
                    trunkInterfaces[face.text] =  total_text
            vlan_info[standard_name]["trunks"] = trunkInterfaces.copy()
        return vlan_info      