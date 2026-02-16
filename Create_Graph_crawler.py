from pyats_genie_command_parse import GenieCommandParse
from pyats.topology import Testbed, loader, Device, Interface, Link
import yaml
import sys
import traceback
import re
import fire
import getpass
import networkx as nx
import matplotlib.pyplot as plt
import pickle
from pyats.utils.secret_strings import SecretString


class Crawl_create:
    def __init__(self,test_bed_name = "default", os="ios", user = "", password = "", device_name = "first_device", ip_address = "", mgm_vlan="115"):
        if not user:
            user = input("Username: ")
        if not password:
            password = SecretString.from_plaintext(getpass.getpass(prompt="password: "))
        self.user = user
        self.os = "ios"
        self.password = password
        self.graph = nx.MultiGraph()
        self.mgm_vlan = "Vlan"+mgm_vlan
        self.__explore_first_switch(device_name,ip_address)
    
    def __explore_first_switch(self, device_name, ip_address):
        first_device = self._create_Testbed_device(device_name, ip_address)
        cdp, version, vlanIP, connected = self._get_cdp_info(first_device)

        if connected:
            self.__cdp_crawler(self._get_ID(vlanIP,version),cdp,version,vlanIP,None)

        
    def __cdp_crawler(self,start,cdp, version, vlanIP, visited):
        if visited is None:
            visited = set()
        visited.add(start)
        for neighbor in cdp["index"]:
            if neighbor not in cdp:
                    first_device = self._create_Testbed_device(neighbor["device_name"], neighbor["ip_address"])
                    cdp1, version1, vlanIP1, connected1 = self._get_cdp_info(first_device)
                    if connected1:
                        self.__cdp_crawler(version1["version"]["chassis_sn"],cdp1,version1,vlanIP1,visited)

    
    def _create_Testbed_device(self,new_device_name,ip_address):
        new_device = Device(new_device_name,
                            os = self.os,
                            connections = {'cli':
                                        {'protocol':'ssh',
                                        'ip' : ip_address}},
                            credentials = {"default":{
                                            "username":self.user,
                                            "password":self.password },}
                        )
        return new_device
    
    def _get_ID(self,vlanIP,version):
        try:
            mgmIP = vlanIP[self.mgm_vlan]["ipv4"].keys()[0]
            return mgmIP
        except Exception as e:
            sys.stderr.write(f"Could not find mgmvlan {self.mgm_vlan} {version["version"]["hostname"]} Error is {e} will use host_name as ID")
            return version["version"]["hostname"]
    
    def _get_cdp_info(self,device):
        command = 'show cdp nei detail'
        command2 = "show version"
        command3 = "show ip interface"
        try:
            dev = device
            dev.connect(learn_hostname=True,goto_enable=False,init_exec_commands=[],init_config_commands=[])
            cdp = dev.default.execute(command)
            version =  dev.default.execute(command2)
            VlanIP = dev.default.execute(command3)
            dev.disconnect()
        except Exception as e:
            sys.stderr.write(f"Could not connect to device {device} Error is {e}")  
            traceback.print_exc() 
            return {},{}, False    
        parse_object = GenieCommandParse(nos=dev.os)
        cdp_parsed =  parse_object.parse_string(show_command = command, show_output_data = cdp)
        version_parsed =  parse_object.parse_string(show_command = command2, show_output_data = version)
        vlanIP_parsed =  parse_object.parse_string(show_command = command3, show_output_data = VlanIP)
        return cdp_parsed, version_parsed,vlanIP_parsed, True

    def __shorten_edge_name(self,port):
        try:
            portType = port[:2]
            port_number = re.findall(r"[0-9]/[0-9]/[0-9]*|[0-9]/[0-9]*|[0-9][0-9]*",port)[0]
            return f"{portType}{port_number}"
        except:
            return port

    def __edges_exists(self,local_port,remote_port,device_g,new_device_name_g):
        if (device_g, new_device_name_g) in self.graph.edges:
            for label in self.graph.adj[device_g][new_device_name_g]:
                label1 = self.graph.adj[device_g][new_device_name_g][label]["label"].split("->")[1]
                label2 =  self.graph.adj[device_g][new_device_name_g][label]["label"].split("->")[0]
                if local_port == label1 and remote_port == label2:
                    return True
        return False

    def _add_cdp_device_to_testbed(self, cdp_object, device,version):
        ip_address = ""
        for index in cdp_object['index']:
            new_device_name =  cdp_object['index'][index]['device_id'].split(".")[0] 
            new_device_name_g = new_device_name
            if len(new_device_name.split("-")) > 1:
                new_device_name_g = new_device_name[new_device_name.find("-"):].lstrip("-")
            device_g = device
            if len(device.split("-")) > 1:
                device_g = device[device.find("-"):].lstrip("-")
            software_version = cdp_object["index"][index]["software_version"]
            local_port = self.__shorten_edge_name(cdp_object['index'][index]['local_interface'])
            remote_port = self.__shorten_edge_name(cdp_object['index'][index]['port_id'])
            edge_label =  f"{local_port}->{remote_port}"
            try: 
                ip_address = list(cdp_object['index'][index]["management_addresses"].keys())[0]
            except:
                ip_address = ""
                print(f"{cdp_object['index'][index]['device_id']} does not have a IP address!!!------------------------<<<<<<<<<<<<")
            my_os = "ios" if re.search("ios",software_version,re.IGNORECASE) else software_version.split(",")[0]
            if cdp_object['index'][index]['capabilities'].lower().find("switch")>=0: # and cdp_object['index'][index]['capabilities'].lower().find("router")<0:
                if not self.__edges_exists(local_port,remote_port,device_g,new_device_name_g):
                    self.graph.add_edge(device_g,new_device_name_g,label = edge_label)
                    self.graph.add_node(new_device_name_g,shape="box",label=f"""{new_device_name_g}
{cdp_object['index'][index]['platform']}""")
                    
                self.graph.add_node(device_g,shape="box",label=f"""{device_g}
{testbed.devices[device].connections['cli']['ip']}
{version['version']['chassis']}
{version['version']['chassis_sn']}
{version['version']['version']}""")
                new_device = Device(new_device_name,
                                         os = my_os,
                                         connections = {'cli':
                                                        {'protocol':'ssh',
                                                      'ip' : ip_address}},
                                        credentials = testbed.devices[device].credentials,
                                        )



if __name__ == "__main__":    
    fire.Fire(Crawl_create)
