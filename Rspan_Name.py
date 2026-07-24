import pickle
import pprint
from pyvis.network import Network
import networkx as nx
import fire
import yaml
import csv
import os
from netutils.interface import abbreviated_interface_name, canonical_interface_name
from itertools import groupby
from operator import itemgetter

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
            "DOWN_PORT": {"gi1/0/#":[Vlan#,]},
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
    """  for edge in self.graph.edges:
            myId = self.graph.get_edge_data(edge[0],edge[1])
            for edges in myId:
                if "DOWN_PORT" in self.Rspan_Commands[edge[0]]:
                    for programmed_edege in self.Rspan_Commands[edge[0]]['DOWN_PORT']:
                        short_port = abbreviated_interface_name(programmed_edege)
                        if(myId[edges]['LocalPort'].lower() == short_port.lower()):
                            summ_of_Vlans = self.__summarize_Vlans(self.Rspan_Commands[edge[0]]['DOWN_PORT'][programmed_edege])
                            if(edge[0]=="MCC-PA1-3-3\n10.182.77.225"):
                                print(summ_of_Vlans + "MCC-PA1-3-3")
                            myId[edges]['label'] = summ_of_Vlans"""
    
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
        self.rspan_numbers = []
        for node in self.graph.nodes:
            try:
                rspan_info = int(self.graph.nodes[node]['RSPAN'][0])
            except:
                rspan_info = None
            if rspan_info:
                self.rspan_numbers.append(rspan_info)
    
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
        possible_rspan_numbers = list(range(800,999))
        for rspanned_possible in  possible_rspan_numbers:
            if rspanned_possible not in self.rspan_numbers:
                self.rspan_numbers.append(rspanned_possible)
                self.next_rspan_number = rspanned_possible
                return self.next_rspan_number

    
    def assign_RSPAN_to_non_rspan_nodes(self):
        self.find_rspan_next_number()
        dfs_order = nx.dfs_tree(self.graph,source=self.root_node[0])
        for node in dfs_order.nodes:
            try:
                rspan_info = self.graph.nodes[node]['RSPAN'][0]
            except:
                rspan_info = "0"
            try:
                Serial_Number = self.graph.nodes[node]['Serial_Number']
            except:
                Serial_Number = "None"
            if rspan_info == "0" and Serial_Number != "None" and node != self.root_node[0]:
                self.graph.nodes[node]['RSPAN'] = self.next_rspan_number
                self.graph.nodes[node]['label'] = f"{self.graph.nodes[node]['label']}\n{self.graph.nodes[node]['RSPAN']}"
                self.graph.nodes[node]['RSPAN_NAME'] = f'RSPAN_{node.split("\n")[0]}_{self.next_rspan_number}'
                self.find_rspan_next_number()
                self.Rspan_Commands[node] = {"Local Rspan Vlans": {"RSPAN": {"number": self.graph.nodes[node]['RSPAN'], 
                                                                            "name": self.graph.nodes[node]['RSPAN_NAME'], 
                                                                            "remote-span": True}, 
                                                                            "Source ports": []},
                                            "Carrier Rspan Vlans": {
                                                "RSPAN": []
                                                        },
                                            "active": True
                                            }
            elif rspan_info == "N" and Serial_Number != "None" and node != self.root_node[0]:
                self.graph.nodes[node]['RSPAN'] = self.next_rspan_number
                self.graph.nodes[node]['label'] = f"{self.graph.nodes[node]['label']}\n{self.graph.nodes[node]['RSPAN']}"
                self.graph.nodes[node]['RSPAN_NAME'] = f'RSPAN_{node.split("\n")[0]}_{self.next_rspan_number}'
                self.find_rspan_next_number()
                self.Rspan_Commands[node] = {"Local Rspan Vlans": {"RSPAN": {"number": self.graph.nodes[node]['RSPAN'],  
                                                            "name": self.graph.nodes[node]['RSPAN_NAME'], 
                                                            "remote-span": False}, 
                                                            "Source ports": []},
                                            "Carrier Rspan Vlans": {
                                                "RSPAN": []
                                                        },
                                            "active": True
                                            }
            elif rspan_info != "0" and Serial_Number != "None" and node != self.root_node[0]:
                self.Rspan_Commands[node] = {"Local Rspan Vlans": {"RSPAN": {"number": self.graph.nodes[node]['RSPAN'][0], 
                                                                            "name": self.graph.nodes[node]['host'], 
                                                                            "remote-span": True}, 
                                                                            "Source ports": []},
                                            "Carrier Rspan Vlans": {
                                                "RSPAN": []
                                                        },
                                            "active": True
                                            }
            elif Serial_Number == "None" or node == self.root_node[0]:
                self.Rspan_Commands[node] = {"Local Rspan Vlans": {"RSPAN": {"number": "0", 
                                                            "name": "None", 
                                                            "remote-span": False}, 
                                                            "Source ports": []},
                                            "Carrier Rspan Vlans": {
                                                "RSPAN": []
                                                        },
                                            "active": False
                                            }
    

    def find_all_ports_that_are_not_trunk(self):
        #self.assign_RSPAN_to_non_rspan_nodes()
        self.read_csv_file_Rspan()
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
                    if switch != node:
                            Rspan_currnet_switch = self.Rspan_Commands[node]["Local Rspan Vlans"]['RSPAN']
                            if self.Rspan_Commands[node]['active']:
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
                        if "UP_PORT" not in self.Rspan_Commands[node]:
                            self.Rspan_Commands[node]["UP_PORT"] = {}
                        self.Rspan_Commands[node]["UP_PORT"][current_node_cdp_info['index'][index]['local_interface']] = {"vlan_list":self.Rspan_Commands[future_node]["Carrier Rspan Vlans"]["RSPAN"].copy()}
                        self.Rspan_Commands[node]["UP_PORT"][current_node_cdp_info['index'][index]['local_interface']]["switch_at_other_end"] = f"{current_node_cdp_info['index'][index]['device_id'].split(".")[0]}\n{next(iter(current_node_cdp_info['index'][index]['management_addresses']), None)}"
                        #add actualNextNodein here
                    elif future_node and current_node_cdp_info['index'][index]['device_id'].split(".")[0] == Sub_Graph.nodes[future_node]['host']:
                        if "DOWN_PORT" not in self.Rspan_Commands[node]:
                            self.Rspan_Commands[node]["DOWN_PORT"] = {}
                        local_port = current_node_cdp_info['index'][index]['local_interface']
                        List_of_all_vlans = self.Rspan_Commands[future_node]["Carrier Rspan Vlans"]["RSPAN"].copy()
                        local_vlan = self.Rspan_Commands[future_node]["Local Rspan Vlans"]["RSPAN"]
                        List_of_all_vlans.append(local_vlan)
                        self.Rspan_Commands[node]["DOWN_PORT"][local_port] = {"vlan_list":List_of_all_vlans}
                        self.Rspan_Commands[node]["DOWN_PORT"][local_port]["switch_at_other_end"] = f"{current_node_cdp_info['index'][index]['device_id'].split(".")[0]}\n{next(iter(current_node_cdp_info['index'][index]['management_addresses']), None)}"
                node_count += 1
    
    def __summarize_Vlans(self,RSpan_Trunk_port_vlan):
        vlans = []
        for vlan in RSpan_Trunk_port_vlan['vlan_list']:
            vlans.append(int(vlan['number']))
            # Sort and remove duplicates if your data is unordered
        sorted_data = sorted(set(vlans))
        
        summary = []
        
        # enumerate provides the index; groupby aggregates by (value - index)
        for key, group in groupby(enumerate(sorted_data), lambda x: x[1] - x[0]):
            # Extract just the original numbers from the group
            group_list = [val for idx, val in group]
            
            if len(group_list) == 1:
                summary.append(str(group_list[0]))
            else:
                summary.append(f"{group_list[0]}-{group_list[-1]}")
        return ",".join(summary)
      
    def relabel_edges_for_rspan(self):
        for node in self.Rspan_Commands:
            if "DOWN_PORT" in self.Rspan_Commands[node]:
                for down_port in self.Rspan_Commands[node]["DOWN_PORT"]:
                    edges = self.graph.get_edge_data(node,self.Rspan_Commands[node]["DOWN_PORT"][down_port]["switch_at_other_end"])
                    short_port_down = abbreviated_interface_name(down_port)
                    for edge in edges:
                        if edges[edge]["LocalPort"].lower() == short_port_down.lower() or edges[edge]["RemotePort"].lower() == short_port_down.lower():
                            summ_of_Vlans = self.__summarize_Vlans(self.Rspan_Commands[node]['DOWN_PORT'][down_port])
                            edges[edge]['label'] = summ_of_Vlans


    def print_map_with_new_Rspan_scheme(self):
        self.find_up_and_down_ports()
        self.relabel_edges_for_rspan()
        viz = nx.nx_agraph.to_agraph(self.graph)
        file_name=f"{self.test_bed_name}"
        viz.draw(f"{file_name}.png",prog="dot")

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
                if 'DOWN_PORT' in self.Rspan_Commands[node]:
                    for down_port in self.Rspan_Commands[node]['DOWN_PORT']:
                        print(f"interface {down_port}")
                        transiant_vlan_numbers = [str(vlan['number']) for vlan in self.Rspan_Commands[node]['DOWN_PORT'][down_port]]
                        print(f"switchport trunk allowed vlan add {','.join(transiant_vlan_numbers)}")
                transiant_vlan_numbers = []
                # Add Transiant and local RSPAN vlans to the up_port Trunk
                if 'UP_PORT' in self.Rspan_Commands[node]:
                    for up_port in self.Rspan_Commands[node]['UP_PORT']:
                        print(f"interface {up_port}")
                        transiant_vlan_numbers = [str(vlan['number']) for vlan in self.Rspan_Commands[node]['Carrier Rspan Vlans']['RSPAN']]
                        all_vlan_numbers = transiant_vlan_numbers + [str(self.Rspan_Commands[node]['Local Rspan Vlans']['RSPAN']['number'])]
                        print(f"switchport trunk allowed vlan add {','.join(all_vlan_numbers)}")
                print("!")
                print("!")
                print("!")
                print("!")

    def create_list_of_Vlans_for_network(self):
        self.find_up_and_down_ports()
        print("Vlan Switch,IP_add ,Vlan Number, Vlan Name, Model")
        for node in self.graph.nodes:
            if 'Model' in self.graph.nodes[node]:
                print(f"{self.graph.nodes[node]['host']},{self.graph.nodes[node]['ip_add']},{self.Rspan_Commands[node]["Local Rspan Vlans"]["RSPAN"]["number"]},{self.Rspan_Commands[node]["Local Rspan Vlans"]["RSPAN"]["name"]},{self.graph.nodes[node]['Model']}")

    def read_csv_file_Rspan(self):
        with open('Rspan_VlanIDS.csv', mode='r', encoding='utf-8') as file:
            # Pass the file object to DictReader
            reader = csv.DictReader(file)
            
            # Convert all rows into a list of dictionaries
            data_dict = list(reader)

        for data in data_dict:
            data["id"] = f"{data["Name"]}\n{data["Ip"]}"
            try:
                rspan_info = self.graph.nodes[data["id"]]['RSPAN'][0]
            except:
                rspan_info = "0"
            try:
                Serial_Number = self.graph.nodes[data["id"]]['Serial_Number']
            except:
                Serial_Number = "None"
            if rspan_info == "0" and Serial_Number != "None" and data["id"] != self.root_node[0]:
                self.graph.nodes[data["id"]]['RSPAN'] = data["Rspan"]
                self.graph.nodes[data["id"]]['label'] = f"{"\n".join(self.graph.nodes[data["id"]]['label'].splitlines()[:-1])}\n{self.graph.nodes[data["id"]]['RSPAN']}"
                self.graph.nodes[data["id"]]['RSPAN_NAME'] = f'RSPAN_{data["Name"]}_{data["Rspan"]}'
                self.Rspan_Commands[data["id"]] = {"Local Rspan Vlans": {"RSPAN": {"number": self.graph.nodes[data["id"]]['RSPAN'], 
                                                                            "name": self.graph.nodes[data["id"]]['RSPAN_NAME'], 
                                                                            "remote-span": True}, 
                                                                            "Source ports": []},
                                            "Carrier Rspan Vlans": {
                                                "RSPAN": []
                                                        },
                                            "active": True
                                            }
            elif rspan_info == "N" and Serial_Number != "None" and data["id"] != self.root_node[0]:
                self.graph.nodes[data["id"]]['RSPAN'] = data["Rspan"]
                self.graph.nodes[data["id"]]['label'] = f"{"\n".join(self.graph.nodes[data["id"]]['label'].splitlines()[:-1])}\n{self.graph.nodes[data["id"]]['RSPAN']}"
                self.graph.nodes[data["id"]]['RSPAN_NAME'] = f'RSPAN_{data["Name"]}_{data["Rspan"]}'
                self.Rspan_Commands[data["id"]] = {"Local Rspan Vlans": {"RSPAN": {"number": self.graph.nodes[data["id"]]['RSPAN'],  
                                                            "name": self.graph.nodes[data["id"]]['RSPAN_NAME'], 
                                                            "remote-span": False}, 
                                                            "Source ports": []},
                                            "Carrier Rspan Vlans": {
                                                "RSPAN": []
                                                        },
                                            "active": True
                                            }
            elif rspan_info != "0" and Serial_Number != "None" and data["Name"] != self.root_node[0]:
                self.graph.nodes[data["id"]]['RSPAN'] = data["Rspan"]
                self.graph.nodes[data["id"]]['label'] = f"{"\n".join(self.graph.nodes[data["id"]]['label'].splitlines()[:-1])}\n{self.graph.nodes[data["id"]]['RSPAN']}"
                self.Rspan_Commands[data["id"]] = {"Local Rspan Vlans": {"RSPAN": {"number": data["Rspan"], 
                                                                            "name": self.graph.nodes[data["id"]]['host'], 
                                                                            "remote-span": True}, 
                                                                            "Source ports": []},
                                            "Carrier Rspan Vlans": {
                                                "RSPAN": []
                                                        },
                                            "active": True
                                            }
            elif Serial_Number == "None" or data["Name"] == self.root_node[0]:
                self.Rspan_Commands[data["id"]] = {"Local Rspan Vlans": {"RSPAN": {"number": "0", 
                                                            "name": "None", 
                                                            "remote-span": False}, 
                                                            "Source ports": []},
                                            "Carrier Rspan Vlans": {
                                                "RSPAN": []
                                                        },
                                            "active": False
                                            }
    
        


if __name__ == "__main__":
    fire.Fire(FindShortestPath)