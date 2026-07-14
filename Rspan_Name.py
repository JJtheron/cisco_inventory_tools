import pickle
import pprint
from pyvis.network import Network
import networkx as nx
import fire
import yaml
import os

class FindShortestPath:
    """
    A class that loads and deserializes a pickle file, storing the data
    in an instance variable accessible throughout the class.
    Graph Node looks like this:
        {id}
        {snmp_location}
        {current_switch_model}
        {current_switch_SN}
        {my_os} {current_switch_FW}
        RSPAN{monitor_info_parsed},
        color={'background': 'white', 'border': 'black'},
        ip_add = id.split("\n")[1],host=id.split("\n")[0], 
        RSPAN=monitor_info_parsed, 
        SNMP_Location=snmp_location, 
        Model=current_switch_model, 
        Serial_Number=current_switch_SN, 
        OS=my_os, 
        Firmware=current_switch_FW
        
    Edges look like this:
        id, <- One switch ID
        new_switch_id, <- Other switch ID
        label = edge_label,
        LocalPort=local_port,
        RemotePort=remote_port,
        Trunk1=trunk1,Trunk2="",
        color="red" if SPT_blocked else "black"
    
    Datastructure for IOS commands on each switch for the Rspan configuration and trunk configurations:
    Rspan_Commands = {
        "switch_id": {
            "UP_PORT": "gi1/0/#",
            "DOWN_PORT": "gi1/0/#",
            "Carrier Rspan Vlans": {
                "RSPAN": [{"number": ###,
                        "name": "Name_of_RSPAN_VLAN",
                        "remote-span": True
                        "trunks": []
                        }
            "Local Rspan Vlans": {
                "RSPAN": { "number": ###,
                        "name": "Name_of_RSPAN_VLAN",
                        "remote-span": True
                        }
                Source ports: ["Gi1/0/#","", ""]
            }
        }
    }
    """
    
    def __init__(self, pickle_file_path, test_bed_name, root_nodeIP):
        """
        Initializes the FindShortestPath with a pickle file path.
        
        Args:
            pickle_file_path (str): The path to the pickle file to load.
            test_bed_name (str): The name of the test bed.
        """
        with open(pickle_file_path, 'rb') as f:
            self.graph = pickle.load(f)
        self.test_bed_name = test_bed_name
        os.makedirs(self.test_bed_name, exist_ok=True)
        self.root_node = [root for root in self.graph.nodes if self.graph.nodes[root]['ip_add'] == root_nodeIP]
        if not self.root_node:
            raise ValueError("Root node not found")
        elif len(self.root_node) > 1:
            raise ValueError("Multiple root nodes found")
        self.Rspan_paths = {}
        self.Rspan_Commands = {}
    
    def loop_through_graph(self):
        for node in self.graph.nodes:
            if node != self.root_node[0]:
                try:
                    Serial_Number = self.graph.nodes[node]['Serial_Number']
                except:
                    Serial_Number = "None"
                try:
                    if Serial_Number != "None":
                        path = nx.shortest_path(self.graph, source=self.root_node[0], target=node, weight='weight')
                        self.Rspan_paths[node] = path
                except nx.NetworkXNoPath:
                    self.Rspan_paths[node] = None
    
    def plot_sub_Graph(self, Path_list, file_name):
        Sub_Graph = self.graph.subgraph(Path_list)
        viz = nx.nx_agraph.to_agraph(Sub_Graph)
        viz.draw(f"{file_name}.png",prog="dot")

    """Plot all the subgraphs and put them in a folder named after the test bed name"""
    def plot_all_sub_Graphs(self):
        self.loop_through_graph()
        for node, path in self.Rspan_paths.items():
            if path is not None:
                file_name = f"{self.test_bed_name}/{node.replace('\n', "").replace('.', '_')}_path"
                self.plot_sub_Graph(path, file_name)

    """Loop through the entire graph and looking at all the Rpan numbers and find the next one to use for the next Rspan VLAN"""
    def find_rspan_next_number(self):
        rspan_numbers = []
        for node in self.graph.nodes:
            try:
                rspan_info = int(self.graph.nodes[node]['RSPAN'][0])
            except:
                rspan_info = None
            if rspan_info:
                rspan_numbers.append(rspan_info)
        if rspan_numbers:
            self.next_rspan_number = max(rspan_numbers) + 1
    
    def assign_RSPAN_to_non_rspan_nodes(self):
        self.find_rspan_next_number()
        for node in self.graph.nodes:
            try:
                rspan_info = self.graph.nodes[node]['RSPAN'][0]
            except:
                rspan_info = "0"
            try:
                Serial_Number = self.graph.nodes[node]['Serial_Number']
            except:
                Serial_Number = "None"
            if rspan_info == "0" and Serial_Number != "None":
                self.graph.nodes[node]['RSPAN'] = self.next_rspan_number
                self.graph.nodes[node]['RSPAN_NAME'] = f'RSPAN_{node.split("\n")[0]}_{self.next_rspan_number}'
                self.next_rspan_number += 1
                self.Rspan_Commands[node] = {"Local Rspan Vlans": {"RSPAN": {"number": self.graph.nodes[node]['RSPAN'], 
                                                                            "name": self.graph.nodes[node]['RSPAN_NAME'], 
                                                                            "remote-span": True}, 
                                                                            "Source ports": []},
                                            "Carrier Rspan Vlans": {
                                                "RSPAN": []
                                                        }
                                            }
            elif rspan_info == "N":
                self.Rspan_Commands[node] = {"Local Rspan Vlans": {"RSPAN": {"number": "0", 
                                                            "name": "None", 
                                                            "remote-span": False}, 
                                                            "Source ports": []},
                                            "Carrier Rspan Vlans": {
                                                "RSPAN": []
                                                        }
                                            }
            elif rspan_info != "0" and Serial_Number != "None":
                self.Rspan_Commands[node] = {"Local Rspan Vlans": {"RSPAN": {"number": self.graph.nodes[node]['RSPAN'][0], 
                                                                            "name": self.graph.nodes[node]['host'], 
                                                                            "remote-span": True}, 
                                                                            "Source ports": []},
                                            "Carrier Rspan Vlans": {
                                                "RSPAN": []
                                                        }
                                            }
            elif Serial_Number == "None":
                self.Rspan_Commands[node] = {"Local Rspan Vlans": {"RSPAN": {"number": "0", 
                                                            "name": "None", 
                                                            "remote-span": False}, 
                                                            "Source ports": []},
                                            "Carrier Rspan Vlans": {
                                                "RSPAN": []
                                                        }
                                            }

    def find_all_ports_that_are_not_trunk(self):
        self.assign_RSPAN_to_non_rspan_nodes()
        for node in self.Rspan_Commands:
            try:
                for port in self.graph.nodes[node]["portInfo"]['interfaces']:
                    access_port = True
                    for trunk in self.graph.nodes[node]["Trunk"]["interface"]:
                        if port == trunk:
                            access_port = False
                            break
                    if access_port:
                        self.Rspan_Commands[node]["Local Rspan Vlans"]["Source ports"].append(port)
            except Exception as e:
                print(f"Error processing node {node}: {e}")
                continue

    """Find All transiant Vlans for each Switch so all switches that are below it in the subgraphs"""
    def find_all_transiant_vlans(self):
        self.loop_through_graph()
        self.find_all_ports_that_are_not_trunk()
        for node, path in self.Rspan_paths.items():
            if path is not None:
                for switch in path:
                    if switch == node:
                        continue
                    elif switch != node:
                            Rspan_currnet_switch = self.Rspan_Commands[node]["Local Rspan Vlans"]['RSPAN']
                            if Rspan_currnet_switch["number"] != "0":
                                self.Rspan_Commands[switch]["Carrier Rspan Vlans"]["RSPAN"].append(Rspan_currnet_switch)
                
        # print(self.Rspan_Commands)
    """ Loop through the Sub Graphs for each Rspan segment no the current previos and future switch. 
    Look up the future and past switches in CDP NEI get the ports from that, 
    the up port will the port from the last iteration and the down purt will be the port for the next iteration"""
    def find_up_and_down_ports(self):
        self.find_all_transiant_vlans()
        for path in self.Rspan_paths:
            node_count = 0
            Sub_Graph = self.graph.subgraph(self.Rspan_paths[path])
            for node in self.Rspan_paths[path]:
                past_node = None
                current_node_cdp_info = None
                past_node = None
                if node_count != 0:
                    past_node = self.Rspan_paths[path][node_count-1]
                current_node_cdp_info = self.graph.nodes[self.Rspan_paths[path][node_count]]['cdp_info']
                if node_count != len(self.Rspan_paths[path])-1:
                    future_node = self.Rspan_paths[path][node_count+1]
                for index in current_node_cdp_info['index']:
                    if past_node and current_node_cdp_info['index'][index]['device_id'].split(".")[0] == Sub_Graph.nodes[past_node]['host']:
                        self.Rspan_Commands[node]["Local Rspan Vlans"]["UP_PORT"] = current_node_cdp_info['index'][index]['local_interface']
                    elif future_node and current_node_cdp_info['index'][index]['device_id'].split(".")[0] == Sub_Graph.nodes[future_node]['host']:
                        self.Rspan_Commands[node]["Local Rspan Vlans"]["DOWN_PORT"] = current_node_cdp_info['index'][index]['local_interface']
                node_count += 1

    def create_cisco_ios_monitor_session_commands(self):
        self.find_up_and_down_ports()
        for node in self.Rspan_Commands:
            if self.Rspan_Commands[node]["Local Rspan Vlans"]["RSPAN"]["number"] != "0":
                transiant_vlan_numbers = []
                print(f"Switch: {node.split('\n')[0]}")
                print(f"vlan {self.Rspan_Commands[node]['Local Rspan Vlans']['RSPAN']['number']}")
                print(f"name {self.Rspan_Commands[node]['Local Rspan Vlans']['RSPAN']['name']}")
                print("remote-span")
                ports_spanned = ",".join(self.Rspan_Commands[node]['Local Rspan Vlans']['Source ports'])
                print(f"monitor session 1 source interface {ports_spanned}")
                print(f"monitor session 1 destination remote {self.Rspan_Commands[node]['Local Rspan Vlans']['RSPAN']["number"]}")
                # Set transiant vlans for all switches in the path
                for transiant_vlan in self.Rspan_Commands[node]['Carrier Rspan Vlans']['RSPAN']:
                    print(f"vlan {transiant_vlan['number']}")
                    print(f"name {transiant_vlan['name']}")
                    print("remote-span")
                # Add all traniant vlans to the down_port Trunk
                if 'DOWN_PORT' in self.Rspan_Commands[node]['Local Rspan Vlans']:
                    print(f"interface {self.Rspan_Commands[node]['Local Rspan Vlans']['DOWN_PORT']}")
                    transiant_vlan_numbers = [str(vlan['number']) for vlan in self.Rspan_Commands[node]['Carrier Rspan Vlans']['RSPAN']]
                    print(f"switchport trunk allowed vlan add {','.join(transiant_vlan_numbers)}")
                transiant_vlan_numbers = []
                # Add Transiant and local RSPAN vlans to the up_port Trunk
                if 'UP_PORT' in self.Rspan_Commands[node]['Local Rspan Vlans']:
                    print(f"interface {self.Rspan_Commands[node]['Local Rspan Vlans']['UP_PORT']}")
                    transiant_vlan_numbers = [str(vlan['number']) for vlan in self.Rspan_Commands[node]['Carrier Rspan Vlans']['RSPAN']]
                    all_vlan_numbers = transiant_vlan_numbers + [str(self.Rspan_Commands[node]['Local Rspan Vlans']['RSPAN']['number'])]
                    print(f"switchport trunk allowed vlan add {','.join(all_vlan_numbers)}")
                print("!")
                print("!")
                print("!")
                print("!")

if __name__ == "__main__":
    fire.Fire(FindShortestPath)