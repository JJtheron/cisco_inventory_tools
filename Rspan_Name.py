import pickle
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
    
    def loop_through_graph(self):
        for node in self.graph.nodes:
            if node != self.root_node[0]:
                try:
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

if __name__ == "__main__":
    fire.Fire(FindShortestPath)