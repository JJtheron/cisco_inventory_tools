from genie.testbed import load
from pyats_genie_command_parse import GenieCommandParse
from pyats.topology import Testbed, loader, Device, Interface, Link
from pyats.utils.secret_strings import SecretString
from pyats.topology.exceptions import DuplicateDeviceError
import pprint
import yaml
import sys
import traceback
import re
import fire
import getpass
#from anytree import Node
from anytree.exporter import DotExporter
from anytree.resolver import Resolver
from anytree import NodeMixin

class Switch(object):
     switch_info = {}
     name = ""
class Switching_Network(Switch,NodeMixin):
    def __init__(self,name,switch_info={},parent=None,children=None):
        super(Switching_Network,self).__init__()
        self.name = name
        self.switch_info = switch_info
        self.parent = parent
        if children:
            self.children = children
    
def edge_attribute(node,child):
    return 'label="%s->%s"' % (child.switch_info['local_interface'],child.switch_info['port_id'])

def node_get_name(node):
    if node.switch_info:
       return f""" {node.name}
{node.switch_info['chassis']}
{node.switch_info['management_addresses']}
{node.switch_info['software_version']}
{node.switch_info['SN']}
                """
    else:
       return node.name

class Crawl_create:
    def __init__(self,test_bed_name = "default", os="ios", user = "", password = "", device_name = "first_device", ip_address = "", protocol = "ssh", port = "22"):
        if not user:
            user = input("Username: ")
        if not password:
            password = getpass.getpass(prompt="password: ")
        self.user = user
        self.password = password
        self.testbed = Testbed(test_bed_name,
                               credentials = {"default":{
                                                "username":user,
                                                "password":password
                               } })

        self.testbed.add_device(Device(device_name,os=os,connections={"cli":{
                                "protocol":protocol,
                                "ip":ip_address,
                                "port":port
        }}))
        self.tree  = Switching_Network(device_name,{})
        self.top = self.tree
        self.visited_switches = []
        self.cdp_crawler(self.testbed,self.tree)    
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

    #check within one lovel of the tree to find location
    def _search_within(self,tree,device):
        if not tree:
            return None
        if device == tree.name:
            return tree
        top = tree
        for child in tree.children:
            newTree =  self._search_within(child,device)
            if newTree:
                return newTree
    

    def _add_cdp_device_to_testbed(self, cdp_object,testbed, device,tree):
        ip_address = ""
        for index in cdp_object['index']:
#            if cdp_object['index'][index]['device_id'].split(".")[0] not in [i.split(".")[0] for i in list(testbed.devices.keys())]:
            software_version = cdp_object["index"][index]["software_version"]  
            nodeName = cdp_object['index'][index]['device_id'].split(".")[0]
            new_node = Switching_Network(nodeName,{},parent=tree)
            try: 
                ip_address = list(cdp_object['index'][index]["management_addresses"].keys())[0]
            except:
                ip_address = ""
                print(f"{cdp_object['index'][index]['device_id']} does not have a IP address!!!------------------------<<<<<<<<<<<<")
            my_os = "ios" if re.search("ios",software_version,re.IGNORECASE) else software_version.split(",")[0]
            new_node.switch_info['management_addresses'] = ip_address
            new_node.switch_info['chassis'] = cdp_object['index'][index]["platform"]
            new_device = Device(cdp_object['index'][index]['device_id'].split(".")[0],
                                     os = my_os,
                                     connections = {'cli':
                                                    {'protocol':'ssh',
                                                  'ip' : ip_address}},
                                    credentials = testbed.devices[device].credentials,
                                    )
            if ip_address:
                try:
                    testbed.add_device(new_device)
                except (DuplicateDeviceError):
                    pass
        return testbed,tree
#TODO: LLDP crawler

#CDP crawler:
    def cdp_crawler(self,testbed,tree):
        dev_copy = testbed.devices.copy()
        cdp = {}
        for device in dev_copy:
            device = device.split(".")[0]
            if device not in self.visited_switches:
                tree = self._search_within(tree.root,device)
                cdp, testbed, version = self._get_cdp_info(testbed,device)
                if cdp and version:
                    testbed,tree = self._add_cdp_device_to_testbed(cdp,testbed, device ,tree)
                    tree.switch_info["chassis"] = version['version']["chassis"]
                    tree.switch_info["software_version"] = version['version']['version']
                    tree.switch_info["SN"] = version['version']['chassis_sn']


                #Go down one level in the search tree
                self.cdp_crawler(testbed,tree)
        self.tree = tree
        self.testbed = testbed
        return testbed, tree

#functions for crawling through environment using cdp
#-----------------------------------------------------------------------------------------------------------------
#^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    def create_ats_testbed_file(self):
        first_device = list(self.testbed.devices.keys())[0]
        topology_dict = {"devices":{},"testbed":{
            "name": self.testbed.name,
            "credentials":{"default":{
                                      "username":self.user,
                                      "password":SecretString.from_plaintext(self.password).data
                        }}}}
        for device in self.testbed.devices:
            try:
                my_ip = str(self.testbed.devices[device].connections.cli.ip)
            except:
                my_ip = self.testbed.devices[device].connections.cli.ip
            topology_dict["devices"][device] = {
                "connections":{"cli":{
                            "ip": my_ip,
                            "protocol":"ssh"
                }},
                        "os":self.testbed.devices[device].os,
                    }
            
        with open(f"{self.testbed.name}.yml", 'w') as tbfile:
            yaml.dump(topology_dict,tbfile)
        return topology_dict

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
    
    def print_out_map(self):
        dot = DotExporter(self.top,edgeattrfunc=edge_attribute,
                          nodenamefunc=node_get_name,
                          nodeattrfunc=lambda node: "shape=box")
        dot.to_dotfile(f"{self.testbed.name}.dot")
        dot.to_picture(f"{self.testbed.name}.png")

if __name__ == "__main__":
    fire.Fire(Crawl_create)
