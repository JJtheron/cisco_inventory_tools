from pyats_genie_command_parse import GenieCommandParse
from pyats.topology import Testbed, Device
import yaml
import sys
import traceback
import re
import fire
import getpass
import networkx as nx
import matplotlib.pyplot as plt
import pickle
from ansible_runner import run
from pyvis.network import Network
from pyats.utils.secret_strings import SecretString


class Crawl_create:
    def __init__(self,test_bed_name = "default", os="ios", user = "", password = "", device_name = "first_device", ip_address = "", load_pickle = False, parse_vlan=False, corp_net=False, use_name_as_id=False):
        if not user:
            user = input("Username: ")
        if not password:
            password = SecretString.from_plaintext(getpass.getpass(prompt="password: "))
        self.user = user
        self.os = "ios"
        self.password = password
        self.graph = nx.MultiGraph()
        self.test_bed_name = test_bed_name
        self.corp_net = corp_net
        self.use_name_as_id = use_name_as_id
        if load_pickle:
            self.load_graph_pickle()
            self.print_map()
        else:
            self.__explore_first_switch(device_name,[ip_address])
    
    def __explore_first_switch(self, device_name, ip_address):
        cdp = {}
        version = {}
        Trunk = {}
        connected = False
        ip_working = ""
        monitor_info_parsed = {}
        for ip in ip_address:
            first_device = self._create_Testbed_device(device_name, ip)
            cdp, version, Trunk, connected, monitor_info_parsed, snmp_location, interface_status_parsed = self._get_cdp_info(first_device)
            ip_working = ip
            if connected: break

        if connected:
            id = self._create_standard_name(version["version"]["hostname"],ip_working)
            self.__cdp_crawler(id,version["version"]["hostname"],ip_working,cdp,version,Trunk,None, monitor_info_parsed, snmp_location, interface_status_parsed)

        
    def __cdp_crawler(self,id,host_name,ip_address,cdp, version, Trunk, visited,monitor_info_parsed, snmp_location, interface_status_parsed):
        if visited is None:
            visited = []
        self._add_cdp_device_to_graph(id,host_name,ip_address,cdp,version,Trunk,monitor_info_parsed, snmp_location,interface_status_parsed)
        visited.append(id)
        for index in cdp["index"]:
            if len(list(cdp["index"][index]["entry_addresses"].keys())) > 0:
                ip_address = list(cdp["index"][index]["entry_addresses"].keys())[0]
                next_device = self._create_Testbed_device(cdp["index"][index]["device_id"], ip_address)
                next_device_id = self._create_standard_name(cdp["index"][index]["device_id"].split(".")[0], ip_address)
                if not self.__visited(next_device_id,visited) and not self.__Test_is_router(cdp,index):
                    cdp1, version1, Trunk1, connected1, monitor_info_parsed1, snmp_location1, interface_status_parsed1 = self._get_cdp_info(next_device)
                    if connected1:
                        id = self._create_standard_name(version1["version"]["hostname"],ip_address)
                        self.__cdp_crawler(id,version1["version"]["hostname"],ip_address,cdp1,version1,Trunk1,visited,monitor_info_parsed1, snmp_location1,interface_status_parsed1)
                    else:
                        ip_address = ""
    
    def _get_cdp_info(self,device):
        command = 'show cdp nei detail'
        command2 = "show version"
        command3 = "show interface trunk"
        command4 = "show monitor session remote"
        command5 = "show snmp location"
        command6 = "show interface status"
        try:
            dev = device
            dev.connect(learn_hostname=True,goto_enable=False,init_exec_commands=[],init_config_commands=[],log_stdout=False)
            cdp = dev.default.execute(command)
            version =  dev.default.execute(command2)
            trunk_info = dev.default.execute(command3)
            try:monitor_info = dev.default.execute(command4)
            except:monitor_info = None
            try: snmp_location = dev.default.execute(command5)
            except: snmp_location = "No SNMP Location"
            interface_status = dev.default.execute(command6)
            dev.disconnect()
        except Exception as e:
            sys.stderr.write(f"Could not connect to device {device} Error is {e}")  
            traceback.print_exc() 
            return {},{},{}, False,{},"No SNMP Location",{}   
        parse_object = GenieCommandParse(nos=dev.os)
        cdp_parsed =  parse_object.parse_string(show_command = command, show_output_data = cdp)
        version_parsed =  parse_object.parse_string(show_command = command2, show_output_data = version)
        trunk_info_parsed =  parse_object.parse_string(show_command = command3, show_output_data = trunk_info)
        interface_status_parsed =  parse_object.parse_string(show_command = command6, show_output_data = interface_status)
        if monitor_info:
            monitor_info_parsed =  re.findall(r'Dest RSPAN VLAN\s*:\s*(\d+)', monitor_info)
        else:
            monitor_info_parsed = "NA"
        return cdp_parsed, version_parsed,trunk_info_parsed, True, monitor_info_parsed, snmp_location, interface_status_parsed


    def _add_cdp_device_to_graph(self, id ,host_name,ip_address,cdp_object,version,Trunk,monitor_info_parsed, snmp_location, interface_status_parsed):
        current_switch_model = version["version"]["chassis"]
        current_switch_SN = version["version"]["chassis_sn"]
        current_switch_FW = version["version"]["version"]
        my_os = version["version"]["os"]
        self.graph.add_node(id,shape="box",label=f"""{host_name}
{ip_address}
{snmp_location}
{current_switch_model}
{current_switch_SN}
{my_os} {current_switch_FW}
RSPAN{monitor_info_parsed}""",color={'background': 'white', 'border': 'black'},ip_add = ip_address,host=host_name, RSPAN=monitor_info_parsed, SNMP_Location=snmp_location, Model=current_switch_model, Serial_Number=current_switch_SN, OS=my_os, Firmware=current_switch_FW, Trunk=Trunk, portInfo=interface_status_parsed, cdp_info=cdp_object)
        ip_address = ""
        for index in cdp_object['index']:
            new_device_name =  cdp_object['index'][index]['device_id'].split(".")[0]
            edge_label, local_port, remote_port =  self.__create_port_label(cdp_object,index,Trunk)
            try: 
                if len(list(cdp_object['index'][index]["entry_addresses"].keys())) > 0:
                    ip_address = list(cdp_object['index'][index]["entry_addresses"].keys())[0]
            except:
                ip_address = ""
                print(f"{new_device_name} does not have a IP address!!!------------------------<<<<<<<<<<<<")
            new_switch_id = self._create_standard_name(new_device_name,ip_address)
            index_of_edge = self.__edges_exists(local_port,remote_port,id,new_switch_id)
            if cdp_object['index'][index]['capabilities'].lower().find("switch")>=0 and not self.__Test_is_router(cdp_object,index):
                if index_of_edge is None:
                    trunk1, SPT_blocked = self.__get_trunk_vlans_allowed(Trunk,cdp_object['index'][index]['local_interface'])
                    self.graph.add_edge(id,new_switch_id,label = edge_label,LocalPort=local_port,RemotePort=remote_port,Trunk1=trunk1,Trunk2="",color="red" if SPT_blocked else "black",weight=9999 if SPT_blocked else 1)
                    self.graph.add_node(new_switch_id,shape="box",label=f"""{new_switch_id}""",color={'background': 'white', 'border': 'red'},ip_add=ip_address,host=new_device_name)
                else:
                    trunk2, SPT_blocked  = self.__get_trunk_vlans_allowed(Trunk,cdp_object['index'][index]['local_interface'])
                    self.graph.adj[id][new_switch_id][index_of_edge]["Trunk2"] = trunk2
                    old_label = self.graph.adj[id][new_switch_id][index_of_edge]["label"]
                    self.graph.adj[id][new_switch_id][index_of_edge]["label"] = f"""{old_label}
{trunk2}"""
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
            for index in self.graph.adj[device_g][new_device_name_g]:
                label1 = self.graph.adj[device_g][new_device_name_g][index]["RemotePort"]
                label2 =  self.graph.adj[device_g][new_device_name_g][index]["LocalPort"]
                if local_port == label1 and remote_port == label2:
                    return index
        return None
 
    def __create_port_label(self,cdp_object,index,Trunk):
        local_port = self.__shorten_edge_name(cdp_object['index'][index]['local_interface'])
        remote_port = self.__shorten_edge_name(cdp_object['index'][index]['port_id'])
        TrunkInfo, SPT_blocked = self.__get_trunk_vlans_allowed(Trunk,cdp_object['index'][index]['local_interface'])
        return f"""{TrunkInfo}
{local_port}->{remote_port}""", local_port, remote_port
    
    def __get_trunk_vlans_allowed(self,Trunk,Port):
        for trunk in Trunk["interface"]:
            if trunk.lower() == Port.lower():
                if Trunk["interface"][trunk]["vlans_allowed_active_in_mgmt_domain"].lower() == Trunk["interface"][trunk]["vlans_in_stp_forwarding_not_pruned"].lower():
                    return Trunk["interface"][trunk]["vlans_allowed_on_trunk"], False
                else:
                    return Trunk["interface"][trunk]["vlans_allowed_on_trunk"], True
        return "", False

    def __Test_is_router(self,cdp_object,index):
        if self.corp_net:
            if "platform" in cdp_object['index'][index].keys():
                value1 = "cloud" in cdp_object['index'][index]['platform'].lower() or "poly" in cdp_object['index'][index]['platform'].lower()
                return value1
            else:
                return False
        else:
            return False

    def __visited(self,neighbor,visited):
        print("--------------------------------------------------")
        print(neighbor)
        print("--------------------------------------------------")
        for visit in visited:
                if visit == neighbor:
                    print("---------------------Found One-----------------------------")
                    print(visit)
                    print("-----------------------^^Same^^---------------------------")
                    return True
        return False
    
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
    
        
    def _create_standard_name(self,current_switch_name,ip_working):
        name_standard  = current_switch_name
        if self.use_name_as_id:
            id = current_switch_name
        else:
            id = name_standard+"\n"+ip_working
        return id

#######################################################################################################################
#vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv Output functions go here vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv
#######################################################################################################################

    def print_map(self):
        viz = nx.nx_agraph.to_agraph(self.graph)
        viz.draw(f"{self.test_bed_name}.png",prog="dot")
        file_name = self.save_as_ansible()
        self.save_graph_pickle()
        self.create_pyviz_graph()
#        self.run_basic_net_info_playbook(file_name)
    
    def run_basic_net_info_playbook(self, inventory_file):
        passwords = {}
        playbook = Playbook.load("basic_net_info.yml",)
        playbook.run(inventory=inventory_file)
    
    def create_pyviz_graph(self):
        net = Network(notebook=True,filter_menu=True)
        net.from_nx(self.graph)
        net.repulsion(node_distance=300, central_gravity=0.3, spring_length=200, spring_strength=0.10, damping=0.95)
        net.show(f"{self.test_bed_name}_pyviz.html")

    def save_as_ansible(self):
        planer_wordlist=["ftrimmer","bander","planer","Lucidyne","finish","office"]
        sawmill_wordlist=["btrimmer","bstacker","green","quad","edger","canter","gang","smtrimmer","smstacker"]
        hosts = {}
        for node in self.graph.nodes():
            node_data = self.graph.nodes[node]
            host_entry = {
                'ansible_host': node_data.get('ip_add', ''),
                'ansible_connection': 'network_cli',
                'ansible_network_os': 'ios'
            }
            #I can probably sus out where switches go from here
            for planer in planer_wordlist:
                if planer in self.graph.nodes[node]["SNMP_Location"]:
                    host_entry["location"] = "Planer"

            hosts[node_data.get('host', node)] = host_entry

        testbed = {
            'all': {
                'hosts': hosts
            }
        }

        with open(f"{self.test_bed_name}_inventory.yml", 'w') as f:
            yaml.dump(testbed, f, default_flow_style=False)
        return f"{self.test_bed_name}_inventory.yml"
    
    def save_graph_pickle(self):
        with open(f"{self.test_bed_name}_graph.pkl", 'wb') as f:
            pickle.dump(self.graph, f)

    def load_graph_pickle(self):
        with open(f"{self.test_bed_name}_graph.pkl", 'rb') as f:
            self.graph = pickle.load(f)


if __name__ == "__main__":    
    fire.Fire(Crawl_create)
