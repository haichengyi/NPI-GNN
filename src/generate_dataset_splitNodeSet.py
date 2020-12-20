from openpyxl import load_workbook
import random
import networkx as nx
import pickle
import sys
import os.path as osp
import os
import argparse
import copy
import gc
import numpy

from openpyxl.descriptors.base import Set
from torch import pinverse

sys.path.append(os.path.realpath('.'))

from src.classes import LncRNA
from src.classes import Protein, LncRNA_Protein_Interaction_dataset_1hop_1218, LncRNA_Protein_Interaction_dataset_1hop_1218_InMemory
from src.classes import LncRNA_Protein_Interaction, LncRNA_Protein_Interaction_dataset, LncRNA_Protein_Interaction_inMemoryDataset
from src.classes import LncRNA_Protein_Interaction_dataset_1hop_1220_InMemory

from src.generate_edgelist import read_interaction_dataset
from src.methods import nodeSerialNumber_listIndex_dict_generation, nodeName_listIndex_dict_generation
from src.methods import reset_basic_data

from src.dataset_splitNodeSet import LncRNA_Protein_Interaction_dataset_1hop_1220_splitNodeSet_InMemory

def parse_args():
    parser = argparse.ArgumentParser(description="generate_dataset.")
    parser.add_argument('--projectName', help='project name')
    parser.add_argument('--fold', help='which fold is this')
    # parser.add_argument('--datasetType', help='training or testing or testing_selected')
    parser.add_argument('--interactionDatasetName', default='NPInter2', help='raw interactions dataset')
    parser.add_argument('--inMemory',default=1, type=int, help='1 or 0: in memory dataset or not')
    parser.add_argument('--hopNumber', default=1, type=int, help='hop number of subgraph')
    parser.add_argument('--shuffle', default=1, type=int, help='shuffle interactions before generate dataset')
    parser.add_argument('--noKmer', default=0, type=int, help='Not using k-mer')
    parser.add_argument('--output', default=0, type=int, help='output dataset or not')

    return parser.parse_args()


def return_node_list_and_edge_list():
    global interaction_list, negative_interaction_list, lncRNA_list, protein_list

    node_list = lncRNA_list[:]
    node_list.extend(protein_list)
    edge_list = interaction_list[:]
    edge_list.extend(negative_interaction_list)
    return node_list, edge_list


def read_node2vec_result(path):
    print('read node2vec result')
    node_list, edge_list = return_node_list_and_edge_list()
    serialNumber_listIndex_dict = nodeSerialNumber_listIndex_dict_generation(node_list)

    node2vec_result_file = open(path, mode='r')
    lines = node2vec_result_file.readlines()
    lines.pop(0)    # 第一行包含：节点个数 节点嵌入后的维度
    for line in lines:
        arr = line.strip().split(' ')
        serial_number = int(arr[0])
        arr.pop(0)
        node_list[serialNumber_listIndex_dict[serial_number]].embedded_vector = arr
    
    for node in node_list:
        if len(node.embedded_vector) != 64:
            print('length of node2vec result vector !== 64')
            node.embedded_vector = [0] * 64
    node2vec_result_file.close()


def load_node_k_mer(node_list, node_type, k_mer_path):
    node_name_index_dict = nodeName_listIndex_dict_generation(node_list)   # 节点的名字：节点在其所在的列表中的index
    with open(k_mer_path, mode='r') as f:   # 打开存有k-mer特征的文件
        lines = f.readlines()
        # 读取k-mer文件
        for i in range(len(lines)):
            line = lines[i]
            # 从文件中定位出lncRNA或者protein的名字
            if line[0] == '>':
                node_name = line.strip()[1:]
                if node_name in node_name_index_dict:   # 根据名字在node_list中找到它，把k-mer数据赋予它
                    node = node_list[node_name_index_dict[node_name]]
                    if len(node.attributes_vector) == 0:    # 如果一个node的attributes_vector已经被赋值过，不重复赋值
                    # 如果这个node，已经被赋予过k-mer数据，报出异常
                        if len(node.attributes_vector) != 0:
                            print(node_name, node.node_type)
                            raise Exception('node already have k-mer result')
                        # k-mer数据提取出来，根据node是lncRNA还是protein，给attributes_vector赋值
                        k_mer_vector = lines[i + 1].strip().split('\t')
                        if node_type == 'lncRNA':
                            if len(k_mer_vector) != 64:
                                raise Exception('lncRNA 3-mer error')
                            for number in k_mer_vector:
                                node.attributes_vector.append(float(number))
                            for i in range(49):
                                node.attributes_vector.append(0)
                        if node_type == 'protein':
                            if len(k_mer_vector) != 49:
                                raise Exception('protein 2-mer error')
                            for i in range(64):
                                node.attributes_vector.append(0)
                            for number in k_mer_vector:
                                node.attributes_vector.append(float(number))


def load_exam(noKmer:int, lncRNA_list:list, protein_list:list):
    if noKmer == 0:
        for lncRNA in lncRNA_list:
            if len(lncRNA.attributes_vector) != 113:
                print(len(lncRNA.attributes_vector), lncRNA.name)
                raise Exception('lncRNA.attributes_vector error')
        for protein in protein_list:
            if len(protein.attributes_vector) != 113:
                print(len(protein.attributes_vector), protein.name)
                raise Exception('protein.attributes_vector error')
    
    for lncRNA in lncRNA_list:
        if len(lncRNA.embedded_vector) != 64:
            raise Exception('lncRNA embedded_vector error')
    for protein in protein_list:
        if len(protein.embedded_vector) != 64:
            raise Exception('protein embedded_vector error')


def load_set_interactionSerialNumberPair(path) -> set:
    set_interactionSerialNumberPair = set()
    with open(path, 'r') as f:
        for line in f.readlines():
            line = line.strip()
            line = line.replace('\n', '')
            line = line.replace('(', '')
            line = line.replace(')', '')
            line = line.replace(' ', '')
            arr = line.split(',')
            set_interactionSerialNumberPair.add((int(arr[0]), int(arr[1])))
    return set_interactionSerialNumberPair


def load_intermediate_products(path):
    interaction_list_path = path + f'/interaction_list.txt'
    negative_interaction_list_path = path + f'/negative_interaction_list.txt'
    lncRNA_list_path = path + f'/lncRNA_list.txt'
    protein_list_path = path + f'/protein_list.txt'
    with open(file=interaction_list_path, mode='rb') as f:
        interaction_list = pickle.load(f)
    with open(file=negative_interaction_list_path, mode='rb') as f:
        negative_interaction_list = pickle.load(f)
    with open(file=lncRNA_list_path, mode='rb') as f:
        lncRNA_list = pickle.load(f)
    with open(file=protein_list_path, mode='rb') as f:
        protein_list = pickle.load(f)
    # 重新建立node和interaction的相互包含的关系
    return reset_basic_data(interaction_list, negative_interaction_list, lncRNA_list, protein_list)


def exam_list_all_interaction(list_all_interaction):
    set_key = set()
    num_pos = 0
    num_neg = 0
    for interaction in list_all_interaction:
        key = (interaction.lncRNA.serial_number, interaction.protein.serial_number)
        set_key.add(key)
        if interaction.y == 1:
            num_pos += 1
        elif interaction.y == 0:
            num_neg += 1
        else:
            raise Exception('interaction.y != 1 and interaction.y != 0')
    print(f'number of different interaction: {len(set_key)}, num of positive: {num_pos}, num of negative: {num_neg}')


def read_set_interactionKey(path):
    set_interactionKey = set()
    with open(path, 'r') as f:
        for line in f.readlines():
            arr = line.strip().split(',')
            set_interactionKey.add((int(arr[0]), int(arr[1])))
    return set_interactionKey


def build_dict_serialNumber_node(list_node):
    dict_serialNumber_node = {}
    for node in list_node:
        dict_serialNumber_node[node.serial_number] = node
    return dict_serialNumber_node


def rebuild_all_negativeInteraction(set_negativeInteractionKey):
    global lncRNA_list, protein_list, negative_interaction_list
    dict_serialNumber_lncRNA = build_dict_serialNumber_node(lncRNA_list)
    dict_serialNumber_protein = build_dict_serialNumber_node(protein_list)
    # 根据set_negativeInteractionKey把负样本集构造出来
    for negativeInteractionKey in set_negativeInteractionKey:
        lncRNA_temp = dict_serialNumber_lncRNA[negativeInteractionKey[0]]
        protein_temp = dict_serialNumber_protein[negativeInteractionKey[1]]
        # 构造负样本
        temp_negativeInteraction = LncRNA_Protein_Interaction(lncRNA_temp, protein_temp, 0, negativeInteractionKey)
        negative_interaction_list.append(temp_negativeInteraction)
        lncRNA_temp.interaction_list.append(temp_negativeInteraction)
        protein_temp.interaction_list.append(temp_negativeInteraction)


def exam_set_allInteractionKey_train_test(set_interactionKey_train, set_negativeInteractionKey_train, set_interactionKey_test, set_negativeInteractionKey_test):
    if len(set_interactionKey_train & set_interactionKey_test & set_negativeInteractionKey_train & set_negativeInteractionKey_test) != 0:
        raise Exception('训练集和测试集有重合')


def read_set_serialNumber_node(path):
    set_serialNumber_node = set()
    with open(path, mode='r') as f:
        for line in f.readlines():
            set_serialNumber_node.add(int(line.strip()))
    return set_serialNumber_node


def process_edgelist_from_local(G:nx.Graph):
    G_new = nx.Graph()
    for node in G.nodes:
        G_new.add_node(int(node))
    for edge in G.edges:
        G_new.add_edge(int(edge[0]), int(edge[1]))
    return G_new


def find_test_alone_node():
    global set_interactionKey, set_negativeInteractionKey, set_serialNumber_lncRNA_test, set_serialNumber_protein_test
    # 创建G_whole
    G_whole = nx.Graph()
    G_whole = process_edgelist_from_local(nx.read_edgelist(f'data/graph/{args.projectName}/bipartite_graph.edgelist')) 
    # for interactionKey in set_interactionKey:
    #     G_whole.add_edge(*interactionKey)
    # for negativeInteractionKey in set_negativeInteractionKey:
    #     G_whole.add_edge(*negativeInteractionKey)
    
    print(f'G whole : number of nodes = {G_whole.number_of_nodes()}, number of edges = {G_whole.number_of_edges()}')
    print(f'number of connected components = {len(list(nx.connected_components(G_whole)))}')

    #创建G_train_between
    set_edge_needRemove = set()
    for edge in G_whole.edges:
        if edge[0] in set_serialNumber_lncRNA_test and edge[1] in set_serialNumber_protein_test:
            set_edge_needRemove.add(edge)
        elif edge[0] in set_serialNumber_protein_test and edge[1] in set_serialNumber_lncRNA_test:
            set_edge_needRemove.add(edge)
    print(f'lncRNA和protein都属于测试集的边有：{len(set_edge_needRemove)}个，要被删除')
    for edge_needRemove in set_edge_needRemove:
        G_whole.remove_edge(*edge_needRemove)
    G_train_between = G_whole
    print(f'{args.fold} fold G_train_between : number of nodes = {G_train_between.number_of_nodes()}, number of edges = {G_train_between.number_of_edges()}')
    print(f'number of connected components = {len(list(nx.connected_components(G_train_between)))}')

    #找到测试集中的孤立点
    set_serialNumber_node_alone = set()
    for node in G_train_between:
        if node in set_serialNumber_lncRNA_test or node in set_serialNumber_lncRNA_test:
            if len(G_train_between.adj[node]) == 0:
                set_serialNumber_node_alone.add(node)
    print(f'孤立点数量 = {len(set_serialNumber_node_alone)}')
    # 返回
    return set_serialNumber_node_alone
    


def exam_training_testing_node():
    global lncRNA_list, protein_list, set_serialNumber_lncRNA_train, set_serialNumber_protein_train, set_serialNumber_lncRNA_test, set_serialNumber_protein_test

    print('分析训练集里的lncRNA')
    list_len_interaction_list = []
    for lncRNA in lncRNA_list:
        if lncRNA.serial_number in set_serialNumber_lncRNA_train:
            list_len_interaction_list.append(len(lncRNA.interaction_list))
    print(f'平均相互连接数 = {numpy.mean(list_len_interaction_list)}， 方差 = {numpy.var(list_len_interaction_list)}')

    print('分析训练集里的protein')
    list_len_interaction_list = []
    for protein in protein_list:
        if protein.serial_number in set_serialNumber_protein_train:
            list_len_interaction_list.append(len(protein.interaction_list))
    print(f'平均相互连接数 = {numpy.mean(list_len_interaction_list)}， 方差 = {numpy.var(list_len_interaction_list)}')

    print('分析测试集里的lncRNA')
    list_len_interaction_list = []
    for lncRNA in lncRNA_list:
        if lncRNA.serial_number in set_serialNumber_lncRNA_test:
            list_len_interaction_list.append(len(lncRNA.interaction_list))
    print(f'平均相互连接数 = {numpy.mean(list_len_interaction_list)}， 方差 = {numpy.var(list_len_interaction_list)}')

    print('分析测试集里的protein')
    list_len_interaction_list = []
    for protein in protein_list:
        if protein.serial_number in set_serialNumber_protein_test:
            list_len_interaction_list.append(len(protein.interaction_list))
    print(f'平均相互连接数 = {numpy.mean(list_len_interaction_list)}， 方差 = {numpy.var(list_len_interaction_list)}')
        


if __name__ == "__main__":
    args = parse_args()

    # # 用中间产物，重现相互作用数据集
    # path_intermediate_products_whole = f'data/intermediate_products/{args.projectName}'
    # 重新读取原始相互作用数据集
    interaction_dataset_path = 'data/source_database_data/'+ args.interactionDatasetName + '.xlsx'
    interaction_list, negative_interaction_list,lncRNA_list, protein_list, lncRNA_name_index_dict, protein_name_index_dict, set_interactionKey, \
        set_negativeInteractionKey = read_interaction_dataset(dataset_path=interaction_dataset_path, dataset_name=args.interactionDatasetName)
    
    path_set_allInteractionKey = f'data/set_allInteractionKey/{args.projectName}'
    path_set_negativeInteractionKey_all = path_set_allInteractionKey + '/set_negativeInteractionKey_all'
    set_negativeInteractionKey = read_set_interactionKey(path_set_negativeInteractionKey_all)

    # 重建负样本
    rebuild_all_negativeInteraction(set_negativeInteractionKey)

    path_set_serialNumber_node = f'data/set_serialNumber_node/{args.projectName}'
    path_set_serialNumber_lncRNA_train = path_set_serialNumber_node + f'/set_serialNumber_lncRNA_train_{args.fold}'
    path_set_serialNumber_protein_train = path_set_serialNumber_node + f'/set_serialNumber_protein_train_{args.fold}'
    path_set_serialNumber_lncRNA_test = path_set_serialNumber_node + f'/set_serialNumber_lncRNA_test_{args.fold}'
    path_set_serialNumber_protein_test = path_set_serialNumber_node + f'/set_serialNumber_protein_test_{args.fold}'

    set_serialNumber_lncRNA_train = read_set_serialNumber_node(path_set_serialNumber_lncRNA_train)
    set_serialNumber_protein_train = read_set_serialNumber_node(path_set_serialNumber_protein_train)
    set_serialNumber_lncRNA_test = read_set_serialNumber_node(path_set_serialNumber_lncRNA_test)
    set_serialNumber_protein_test = read_set_serialNumber_node(path_set_serialNumber_protein_test)

    set_serialNumber_node_test_alone = find_test_alone_node()

    exam_training_testing_node()

    # # 把训练集和测试集包含的边读取出来
    # path_set_interactionKey_train = path_set_allInteractionKey + f'/set_interactionKey_train_{args.fold}'
    # path_set_negativeInteractionKey_train = path_set_allInteractionKey + f'/set_negativeInteractionKey_train_{args.fold}'
    # path_set_interactionKey_test = path_set_allInteractionKey + f'/set_interactionKey_test_{args.fold}'
    # path_set_negativeInteractionKey_test = path_set_allInteractionKey + f'/set_negativeInteractionKey_test_{args.fold}'

    # set_interactionKey_train = read_set_interactionKey(path_set_interactionKey_train)
    # set_negativeInteractionKey_train = read_set_interactionKey(path_set_negativeInteractionKey_train)
    # set_interactionKey_test = read_set_interactionKey(path_set_interactionKey_test)
    # set_negativeInteractionKey_test = read_set_interactionKey(path_set_negativeInteractionKey_test)

    # # 检查一下训练集和测试集有没有重合
    # exam_set_allInteractionKey_train_test(set_interactionKey_train, set_negativeInteractionKey_train, set_interactionKey_test, set_negativeInteractionKey_test)

    # load node2vec result
    node2vec_result_path = f'data/node2vec_result/{args.projectName}/training_{args.fold}/result.emb'
    read_node2vec_result(path=node2vec_result_path)

    # load k-mer
    if args.noKmer == 0:
        lncRNA_3_mer_path = f'data/lncRNA_3_mer/{args.interactionDatasetName}/lncRNA_3_mer.txt'
        protein_2_mer_path = f'data/protein_2_mer/{args.interactionDatasetName}/protein_2_mer.txt'
        load_node_k_mer(lncRNA_list, 'lncRNA', lncRNA_3_mer_path)
        load_node_k_mer(protein_list, 'protein', protein_2_mer_path)

    # 执行检查
    load_exam(args.noKmer, lncRNA_list, protein_list)
    
    
    # 数据集生成
    exam_list_all_interaction(interaction_list)
    exam_list_all_interaction(negative_interaction_list)
    all_interaction_list = interaction_list.copy()
    all_interaction_list.extend(negative_interaction_list)
    exam_list_all_interaction(all_interaction_list)

    if args.shuffle == 1:    # 随机打乱
        print('shuffle dataset\n')
        random.shuffle(all_interaction_list)
    
    # num_of_subgraph = len(all_interaction_list)

    if args.output == 1:
        if args.inMemory == 0:
            raise Exception('not ready')
            # dataset_path = f'data/dataset/{args.projectName}'
            # if not osp.exists(dataset_path):
            #     os.makedirs(dataset_path)
            # My_dataset = LncRNA_Protein_Interaction_dataset_1hop_1218(dataset_path, all_interaction_list, 1)
        else:
            # 生成局部子图，不能有测试集的边
            set_serialNumber_node_train = set()
            set_serialNumber_node_train.update(set_serialNumber_lncRNA_train)
            set_serialNumber_node_train.update(set_serialNumber_protein_train)

            set_serialNumber_node_test = set()
            set_serialNumber_node_test.update(set_serialNumber_lncRNA_test)
            set_serialNumber_node_test.update(set_serialNumber_protein_test)

            print(f'训练集和测试集没有重叠:{len(set_serialNumber_node_train & set_serialNumber_node_test) == 0}')
            print(f'训练集和测试集中点的总数：{len(set_serialNumber_node_train) + len(set_serialNumber_node_test)}')

            # 生成训练集
            dataset_train_path = f'data/dataset/{args.projectName}_inMemory_train_{args.fold}'
            if not osp.exists(dataset_train_path):
                print(f'创建了文件夹：{dataset_train_path}')
                os.makedirs(dataset_train_path)
            My_trainingDataset = LncRNA_Protein_Interaction_dataset_1hop_1220_splitNodeSet_InMemory(dataset_train_path, all_interaction_list, 1, 'training', set_serialNumber_node_train, set_serialNumber_node_test, set_serialNumber_node_test_alone )

            # 生成测试集
            dataset_test_path = f'data/dataset/{args.projectName}_inMemory_test_{args.fold}'
            if not osp.exists(dataset_test_path):
                print(f'创建了文件夹：{dataset_test_path}')
                os.makedirs(dataset_test_path)
            My_testingDataset = LncRNA_Protein_Interaction_dataset_1hop_1220_splitNodeSet_InMemory(dataset_test_path, all_interaction_list, 1, 'testing', set_serialNumber_node_train, set_serialNumber_node_test, set_serialNumber_node_test_alone)

            # 生成没有孤立点的测试集
            dataset_test_selected_path = f'data/dataset/{args.projectName}_inMemory_test_selected_{args.fold}'
            if not osp.exists(dataset_test_selected_path):
                print(f'创建了文件夹：{dataset_test_selected_path}')
                os.makedirs(dataset_test_selected_path)
            My_testingDataset = LncRNA_Protein_Interaction_dataset_1hop_1220_splitNodeSet_InMemory(dataset_test_selected_path, all_interaction_list, 1, 'testing_selected', set_serialNumber_node_train, set_serialNumber_node_test, set_serialNumber_node_test_alone)

    exit(0)
