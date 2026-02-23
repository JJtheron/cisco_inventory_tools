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
    def __init__(self,test_bed_name = "default", os="ios", user = "", password = "", device_name = "first_device", ip_address = ""):
        if not user:
            user = input("Username: ")
        if not password:
            password = SecretString.from_plaintext(getpass.getpass(prompt="password: "))
        self.user = user
        self.os = "ios"
        self.password = password
        self.graph = nx.MultiGraph()
        self.test_bed_name = test_bed_name
        self.__explore_first_switch(device_name,[ip_address])
    
    def __explore_first_switch(self, device_name, ip_address):
        cdp = {}
        version = {}
        vlanIP = {}
        connected = False
        ip_working = ""
        for ip in ip_address:
            first_device = self._create_Testbed_device(device_name, ip)
            cdp, version, vlanIP, connected = self._get_cdp_info(first_device)
            ip_working = ip
            if connected: break

        if connected:
            id = self._create_standard_name(version["version"]["hostname"],ip_working)
            self.__cdp_crawler(id,cdp,version,vlanIP,None)
    
    def _create_standard_name(self,current_switch_name,ip_working):
        name_standard  = current_switch_name
        id = name_standard+"\n"+ip_working +"\n"
        return id

    def __visited(self,neighbor,visited):
        for visit in visited:
            try:
                if visit == neighbor:
                    return True
            except:
                return True

        return False

        
    def __cdp_crawler(self,id,cdp, version, vlanIP, visited):
        if visited is None:
            visited = set()
        visited.add(id)
        self._add_cdp_device_to_graph(id, cdp,version)
        for index in cdp["index"]:
            if len(list(cdp["index"][index]["entry_addresses"].keys())) > 0:
                ip_address = list(cdp["index"][index]["entry_addresses"].keys())[0]
                next_device = self._create_Testbed_device(cdp["index"][index]["device_id"], ip_address)
                if not self.__visited(next_device,visited) and not self.__Test_is_router(cdp,index):
                    cdp1, version1, vlanIP1, connected1 = self._get_cdp_info(next_device)
                    if connected1:
                        id = self._create_standard_name(version1["version"]["hostname"],ip_address)
                        self.__cdp_crawler(id,cdp1,version1,vlanIP1,visited)
                    else:
                        ip_address = ""

    
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
            return {},{},{}, False    
        parse_object = GenieCommandParse(nos=dev.os)
        cdp_parsed =  parse_object.parse_string(show_command = command, show_output_data = cdp)
        version_parsed =  parse_object.parse_string(show_command = command2, show_output_data = version)
        vlanIP_parsed =  parse_object.parse_string(show_command = command3, show_output_data = VlanIP)
        return cdp_parsed, version_parsed,vlanIP_parsed, True


    def _add_cdp_device_to_graph(self, id ,cdp_object,version):
        current_switch_model = version["version"]["chassis"]
        current_switch_SN = version["version"]["chassis_sn"]
        current_switch_FW = version["version"]["switch_num"]["1"]["sw_ver"]
        my_os = version["version"]["os"]
        self.graph.add_node(id,shape="box",label=f"""{id}
{current_switch_model}
{current_switch_SN}
{my_os} {current_switch_FW}""",color="black")
        ip_address = ""
        for index in cdp_object['index']:
            new_device_name =  cdp_object['index'][index]['device_id'].split(".")[0]
            edge_label, local_port, remote_port =  self.__create_port_label(cdp_object,index)
            try: 
                if len(list(cdp_object['index'][index]["entry_addresses"].keys())) > 0:
                    ip_address = list(cdp_object['index'][index]["entry_addresses"].keys())[0]
            except:
                ip_address = ""
                print(f"{new_device_name} does not have a IP address!!!------------------------<<<<<<<<<<<<")
            new_switch_id = self._create_standard_name(new_device_name,ip_address)
            if cdp_object['index'][index]['capabilities'].lower().find("switch")>=0 and not self.__Test_is_router(cdp_object,index):
                if not self.__edges_exists(local_port,remote_port,id,new_switch_id):
                    ## JJ was here
                    self.graph.add_edge(id,new_switch_id,label = edge_label)
                    self.graph.add_node(new_switch_id,shape="box",label=f"""{new_switch_id}""",color="red")

#########################################################################################
#vvvvvvvvvvvvvvvvvvvvvvv Helper functions go here  vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv
#########################################################################################
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

    def __create_port_label(self,cdp_object,index):
        local_port = self.__shorten_edge_name(cdp_object['index'][index]['local_interface'])
        remote_port = self.__shorten_edge_name(cdp_object['index'][index]['port_id'])
        return f"{local_port}->{remote_port}", local_port, remote_port
    
    def __Test_is_router(self,cdp_object,index):
        return "cloud managed ap" in cdp_object['index'][index]['platform'].lower() or "Polycom" in cdp_object['index'][index]['platform'].lower()
#######################################################################################################################
#vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv Output functions go here vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv
#######################################################################################################################

    def print_map(self):
        viz = nx.nx_agraph.to_agraph(self.graph)
        viz.draw(f"{self.test_bed_name}.png",prog="dot")

if __name__ == "__main__":    
    fire.Fire(Crawl_create)
