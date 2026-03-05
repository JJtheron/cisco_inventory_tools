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
    def __init__(self,test_bed_name = "default", os="ios", user = "", password = "", device_name = "first_device", ip_address = "", protocol = "ssh", port = "22"):
        if not user:
            user = input("Username: ")
        if not password:
            password = SecretString.from_plaintext(getpass.getpass(prompt="password: "))
        self.user = user
        self.password = password
        self.testbed = Testbed(test_bed_name,
                               credentials = {"default":{
                                                "username":user,
                                                "password":password
                               },

                               })

        self.testbed.add_device(Device(device_name,os=os,connections={"cli":{
                                "protocol":protocol,
                                "ip":ip_address,
                                "port":port
        }}))
        self.visited_switches = []
        self.graph = nx.MultiGraph()
        self.__cdp_crawler(self.testbed)

#functions for crawling through environment using cdp
#-----------------------------------------------------------------------------------------------------------------
#VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV
    def _get_cdp_info(self,testbed,device):
        command = 'show cdp nei detail'
        command2 = "show version"
        try:
            dev = testbed.devices[device]
            dev.connect(learn_hostname=True,goto_enable=False,init_exec_commands=[],init_config_commands=[])
            cdp = dev.default.execute(command)
            version =  dev.default.execute(command2)
            dev.disconnect()
        except Exception as e:
            sys.stderr.write(f"Could not connect to device {device} Error is {e}")  
            self.visited_switches.append(device.split(".")[0])
            traceback.print_exc() 
            return {},testbed,{}
            
        parse_object = GenieCommandParse(nos=dev.os)
        testbed.devices[dev.hostname] = testbed.devices.pop(device)
        cdp_parsed =  parse_object.parse_string(show_command = command, show_output_data = cdp)
        version_parsed =  parse_object.parse_string(show_command = command2, show_output_data = version)
        self.visited_switches.append(dev.hostname)

        return cdp_parsed, testbed, version_parsed

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

    def _add_cdp_device_to_testbed(self, cdp_object,testbed, device,version):
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
                if ip_address and new_device_name not in [i.split(".")[0] for i in list(testbed.devices.keys())]:
                    testbed.add_device(new_device)
        return testbed
#TODO: LLDP crawler

#CDP crawler:
    def __cdp_crawler(self,testbed):
        dev_copy = testbed.devices.copy()
        cdp = {}
        for device in dev_copy:
            device = device.split(".")[0]
            if device not in self.visited_switches:
                cdp, testbed, version = self._get_cdp_info(testbed,device)
                if cdp:
                    testbed = self._add_cdp_device_to_testbed(cdp,testbed, device,version)


                self.__cdp_crawler(testbed)
        self.testbed = testbed
        return testbed

#functions for crawling through environment using cdp
#-----------------------------------------------------------------------------------------------------------------
#^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

    def create_hosts_file_ansible(self):
        ansible_hosts = {"all":{"hosts":{}}}
        for device in self.testbed.devices:
            try:
                my_ip = str(self.testbed.devices[device].connections.cli.ip)
            except:
                my_ip = self.testbed.devices[device].connections.cli.ip
            ansible_hosts["all"]["hosts"][device] = {"ansible_host": my_ip }
        with open(f"ansible_{self.testbed.name}.yml", 'w') as tbfile:
            yaml.dump(ansible_hosts,tbfile)
        return ansible_hosts
    
    def print_map(self,serial_file=""):
        if serial_file:
            f=open(serial_file,'rb')
            graph = pickle.load(f)
            viz = nx.nx_agraph.to_agraph(graph)
            viz.draw(f"test.png",prog="dot")
        else:
            with open(f"{self.testbed.name}.pickle",'wb') as f:
                pickle.dump(self.graph,f)
            viz = nx.nx_agraph.to_agraph(self.graph)
            viz.draw(f"{self.testbed.name}.png",prog="dot")

#        options = {
#                "font_size": 8,
#                "node_size": 3000,
#                "node_color": "white",
#                "edgecolors": "black",
#                "linewidths": 1,
#                "width": 5,
#                "with_labels": True
#        }
#        pos = nx.spring_layout(self.graph)
#        plt.figure(figsize=(24,24))
#        edge_labels = dict([((n1, n2), d['label'])
#                                                for n1, n2, d in self.graph.edges(data=True)])
#        nx.draw_networkx(self.graph,pos,**options)
#        nx.draw_networkx_edge_labels(self.graph,pos,edge_labels=edge_labels)


       # plt.savefig(f"{self.testbed.name}.png")

    
if __name__ == "__main__":
    #Crawl_create.print_map(serial_file="CottageGrove.pickle")    
    fire.Fire(Crawl_create)
