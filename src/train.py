import sys
import os.path as osp
import os
import random
from tqdm import tqdm
import time
import gc
import argparse
sys.path.append(os.path.realpath('.'))

from src.classes import Net_1, LncRNA_Protein_Interaction_dataset, LncRNA_Protein_Interaction_inMemoryDataset
from src.classes import LncRNA_Protein_Interaction_dataset_1hop_1218_InMemory, LncRNA_Protein_Interaction_dataset_1hop_1218

from src.methods import dataset_analysis, average_list, Accuracy_Precision_Sensitivity_Specificity_MCC

from torch_geometric.data import DataLoader

import torch
import torch.nn.functional as F
from torch.optim import *


def parse_args():
    parser = argparse.ArgumentParser(description="generate_dataset.")
    parser.add_argument('--trainingName', help='the name of this training')
    parser.add_argument('--datasetName',  help='the name of this object')
    parser.add_argument('--inMemory', type = int, help='in memory dataset or not')
    parser.add_argument('--interactionDatasetName',default='NPInter2', help='raw interactions dataset')
    parser.add_argument('--epochNumber', default=10, type=int, help='number of training epoch')
    parser.add_argument('--hopNumber', default=2, type=int , help='hop number of subgraph')
    parser.add_argument('--node2vecWindowSize', default=5, type=int, help='node2vec window size')
    parser.add_argument('--crossValidation', default=1, type=int, help='do cross validation')
    parser.add_argument('--foldNumber', default=5, type=int, help='fold number of cross validation')
    parser.add_argument('--initialLearningRate', default=0.005,type=float, help='Initial learning rate')
    parser.add_argument('--l2WeightDecay', default=0.0005, type=float, help='L2 weight')
    parser.add_argument('--batchSize', default=200, type=int, help='batch size')

    return parser.parse_args()


def train():
    model.train()
    loss_all = 0
    for data in train_loader:
        data = data.to(device)
        optimizer.zero_grad()
        output = model(data)
        loss = F.nll_loss(output, data.y)
        loss.backward()
        loss_all += data.num_graphs * loss.item()
        optimizer.step()
    return loss_all / len(train_dataset)


if __name__ == "__main__":
    #参数
    args = parse_args()

    dataset_path = f'./data/dataset/{args.datasetName}'
    # 读取数据集
    if args.inMemory == 0:
        dataset = LncRNA_Protein_Interaction_dataset_1hop_1218(root=dataset_path)
    else:
        dataset = LncRNA_Protein_Interaction_dataset_1hop_1218_InMemory(root=dataset_path)
    # 打乱数据集
    print('shuffle dataset\n')
    dataset = dataset.shuffle()
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    saving_path = f'result/{args.trainingName}'
    if osp.exists(saving_path):
        raise Exception('There is already a training of the same name')
    else:
        os.makedirs(saving_path)

    if args.crossValidation == 1:
        # k折交叉验证
        k = args.foldNumber
        step_length = len(dataset) // k
        
        # 迭代次数
        num_of_epoch = args.epochNumber

        # 学习率
        LR = args.initialLearningRate

        # L2正则化系数
        L2_weight_decay = args.l2WeightDecay

        # 准备log
        log_path = saving_path + '/log.txt'
        result_file = open(file=log_path, mode='w')
        result_file.write(f'database：{args.interactionDatasetName}\n')
        result_file.write(f'node2vec_windowSize = {args.node2vecWindowSize}\n')
        result_file.write(f'{k}-fold cross validation\n')
        result_file.write(f'number of epoch ：{num_of_epoch}\n')
        result_file.write(f'learn rate：initial = {LR}，whenever loss increases, multiply by 0.95\n')
        result_file.write(f'L2 weight decay = {L2_weight_decay}\n')

        # 记录启示时间
        start_time = time.time()
        Accuracy_list = []
        Precision_list = []
        Sensitivity_list = []
        Specificity_list = []
        MCC_list = []
        for i in range(k):
            print('{:d}-fold start'.format(i+1))
            # 创建保存模型的文件夹
            os.makedirs(saving_path + f'/model_{i}_fold')
            # 创建模型
            num_of_classes = 2
            
            if i != 0:
                del model
            gc.collect()
            model = Net_1(dataset.num_node_features, num_of_classes).to(device)
            
            optimizer = torch.optim.Adam(model.parameters(), lr=LR, weight_decay=L2_weight_decay)
            # scheduler = lr_scheduler.MultiStepLR(optimizer,milestones=[int(num_of_epoch * 0.2),int(num_of_epoch * 0.8)],gamma = 0.8)
            scheduler = torch.optim.lr_scheduler.ExponentialLR(optimizer=optimizer, gamma=0.95)

            # 训练集和测试集
            test_dataset_start = 0 + i * step_length
            test_dataset_end = (i + 1) * step_length
            test_dataset = dataset[test_dataset_start:test_dataset_end]
            train_dataset = dataset[0:test_dataset_start] + dataset[test_dataset_end:dataset.len()]

            print('number of samples in testing dataset：', len(test_dataset), 'number of samples in training dataset：', len(train_dataset))
            print('training dataset')
            dataset_analysis(train_dataset)
            print('testing dataset')
            dataset_analysis(test_dataset)

            train_loader = DataLoader(train_dataset, batch_size=args.batchSize)
            test_loader = DataLoader(test_dataset, batch_size=args.batchSize)

            # 训练开始
            loss_last = float('inf')
            for epoch in range(num_of_epoch):
                loss = train()

                # loss增大时,降低学习率
                if loss > loss_last:
                    scheduler.step()
                loss_last = loss

                # 训练中评价模型，监视训练过程中的模型变化, 并且写入文件
                if (epoch + 1) % 5 == 0 and epoch != num_of_epoch - 1:
                    # 用Accuracy, Precision, Sensitivity, MCC评价模型
                    # Accuracy, Precision, Sensitivity ,MCC = Accuracy_Precision_Sensitivity_MCC(model, train_loader, device)
                    Accuracy, Precision, Sensitivity, Specificity, MCC = Accuracy_Precision_Sensitivity_Specificity_MCC(model, train_loader, device)
                    output = 'Epoch: {:03d}, training dataset, Accuracy: {:.5f}, Precision: {:.5f}, Sensitivity: {:.5f}, Specificity: {:.5f}, MCC: {:.5f}'.format(epoch + 1, Accuracy, Precision, Sensitivity, Specificity, MCC)
                    print(output)
                    result_file.write(output + '\n')
                    # Accuracy, Precision, Sensitivity, MCC = Accuracy_Precision_Sensitivity_MCC(model, test_loader, device)
                    Accuracy, Precision, Sensitivity, Specificity, MCC = Accuracy_Precision_Sensitivity_Specificity_MCC(model, test_loader, device)
                    output = 'Epoch: {:03d}, testing dataset, Accuracy: {:.5f}, Precision: {:.5f}, Sensitivity: {:.5f}, Specificity: {:.5f}, MCC: {:.5f}'.format(epoch + 1, Accuracy, Precision, Sensitivity, Specificity, MCC)
                    print(output)
                    result_file.write(output + '\n')
                    # 保存模型
                    network_model_path = saving_path + f'/model_{i}_fold/{epoch+1}'
                    torch.save(model.state_dict(), network_model_path)

            # 训练结束，评价模型，并且把结果写入文件
            Accuracy, Precision, Sensitivity, Specificity, MCC = Accuracy_Precision_Sensitivity_Specificity_MCC(model, train_loader, device)
            output = '{:03d}-fold result, training dataset, Accuracy: {:.5f}, Precision: {:.5f}, Sensitivity: {:.5f}, Specificity: {:.5f}, MCC: {:.5f}'.format(i + 1, Accuracy, Precision, Sensitivity, Specificity, MCC)
            print(output)
            result_file.write(output + '\n')
            Accuracy, Precision, Sensitivity, Specificity, MCC = Accuracy_Precision_Sensitivity_Specificity_MCC(model, test_loader, device)
            output = '{:03d}-fold result, testing dataset, Accuracy: {:.5f}, Precision: {:.5f}, Sensitivity: {:.5f}, Specificity: {:.5f}, MCC: {:.5f}'.format(i + 1, Accuracy, Precision, Sensitivity, Specificity, MCC)
            print(output)

            Accuracy_list.append(Accuracy)
            Precision_list.append(Precision)
            Sensitivity_list.append(Sensitivity)
            Specificity_list.append(Specificity)
            MCC_list.append(MCC)

            result_file.write(output + '\n')
            # 把模型存起来
            network_model_path = saving_path + f'/model_{i}_fold/{num_of_epoch}'
            torch.save(model.state_dict(), network_model_path)

        # k折交叉验证完毕
        end_time = time.time()
        print('Time consuming:', end_time - start_time)
        result_file.write('Time consuming:' + str(end_time - start_time) + '\n')
        

        # 计算平均的Accuracy, Precision, Sensitivity, MCC
        Accuracy_average = average_list(Accuracy_list)
        Precision_average = average_list(Precision_list)
        Sensitivity_average = average_list(Sensitivity_list)
        Specificity_average = average_list(Specificity_list)
        MCC_average = average_list(MCC_list)

        # 输出最终的结果
        print('average result，Accuracy: {:.5f}, Precision: {:.5f}, Sensitivity: {:.5f}, Specificity: {:.5f}, MCC: {:.5f}'.format(Accuracy_average, Precision_average, Sensitivity_average, Specificity_average, MCC_average))
        result_file.write('average result，Accuracy: {:.5f}, Precision: {:.5f}, Sensitivity: {:.5f}, Specificity: {:.5f}, MCC: {:.5f}'.format(Accuracy_average, Precision_average, Sensitivity_average, Specificity_average, MCC_average))

        result_file.close()
        
        print('\nexit\n')