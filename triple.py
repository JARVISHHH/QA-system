import os
import re
import pandas as pd
import numpy as np
import networkx as nx
import matplotlib.pyplot as plt
# matplotlib显示中文和负号问题

import warnings

from collections import defaultdict
from harvesttext import HarvestText
from zincbase import KB

import pickle as pkl

from harvesttext.resources import get_qh_typed_words

# 获得爬虫数据
def get_data():
    with open(os.path.join(os.path.dirname(__file__), "url.txt"), "rb") as file:
        num, str_to_id, id_to_str, skip_urls, text_url, queue_urls = pkl.load(file)
    return text_url

# 保存数据
def save_data():
    with open(os.path.join(os.path.dirname(__file__), "data.txt"), "wb") as file:
        pkl.dump([SVOs, entity_type_dict], file)

# 输出图像
def show_picture(SVOs):
    # 输出图像
    fig = plt.figure(figsize=(12,8),dpi=100)
    g_nx = nx.DiGraph()
    labels = {}
    for subj, pred, obj in SVOs:
        g_nx.add_edge(subj,obj)
        labels[(subj,obj)] = pred
    pos=nx.spring_layout(g_nx)
    nx.draw_networkx_nodes(g_nx, pos, node_size=300)
    nx.draw_networkx_edges(g_nx,pos,width=4)
    nx.draw_networkx_labels(g_nx,pos,font_size=10,font_family='sans-serif')
    nx.draw_networkx_edge_labels(g_nx, pos, labels , font_size=10, font_family='sans-serif')
    plt.axis("off")
    plt.show()

# 使用清华词典建立命名实体词典
def establish_qh_dict():
    qh_typed_words = get_qh_typed_words()
    entity_type_dict = {}
    for word_type in ['IT', '动物', '医药', '历史人名', '地名', '成语', '法律', '财经', '食物']:
        for word in qh_typed_words[word_type]:
            entity_type_dict[word] = "其他专名"
    print("清华词典构建完毕")
    return entity_type_dict

# 使用自己的数据扩充词典
def enrich_type_dict(text_data, ht, entity_type_dict):
    ht.add_entities(entity_type_dict = entity_type_dict)
    # 遍历所有的爬虫数据
    for id in text_data.keys():
        # 仅处理前5个网页（测试时使用）
        # if id > 5:
        #     break

        # 获得网页的文本内容
        doc = text_data[id]["text"]
        # 分句
        sentences = ht.cut_sentences(doc)

        # 遍历所有的句子，扩充命名实体字典
        for i, sent in enumerate(sentences):
            # sent = sent.replace(" ", "")  # 去除空格
            sent = sent.strip()
            # 有一些无用的特殊符号，则跳过
            if "Copyright" in sent or "<title>" in sent or "/title" in sent:
                continue
            # 命名实体识别
            entity_type_dict0 = ht.named_entity_recognition(sent)
            # 将内容加入到实体类型字典中
            for entity0, type0 in entity_type_dict0.items():
                entity_type_dict[entity0] = type0
    print("词典建立完毕")

    return ht, entity_type_dict

# 获得别名词典
def get_mention_dict(text_data, ht):
    processed_texts = []
    for id in text_data.keys():
        doc = text_data[id]["text"]
        sentences = ht.cut_sentences(doc)
        for sent in sentences:
            sent = ht.clean_text(sent, remove_tags=True)
            if len(sent) > 0:
                processed_texts.append(sent)
    em_dict, et_dict = ht.entity_discover("\n".join(processed_texts), method="NFL", threshold=0.97)
    entity_mention_dict = {}
    for entity in em_dict.keys():
        new_entity = entity.replace("_", " ").split(" ")[0]
        entity_mention_dict[new_entity] = em_dict[entity]
    print(entity_mention_dict)
    return entity_mention_dict

# 抽取三元组
def extract_triple(text_data, ht, entity_type_dict):
    SVOs = []  # 三元组列表
    for id in text_data.keys():
        # 仅抽取前5个网页，测试时使用
        # if id > 5:
        #     break

        # 获得网页文本内容
        doc = text_data[id]["text"]
        # 切句
        sentences = ht.cut_sentences(doc)
        inv_index = ht.build_index(sentences)  # 建立索引
        # 遍历所有句子
        for i, sent in enumerate(sentences):
            # sent = sent.replace(" ", "")
            sent = sent.strip()
            if "Copyright" in sent or "<title>" in sent or "/title" in sent:
                continue
            # 如果获得的命名实体小于2个（即一定不可能构成主谓宾），则跳过
            if len(ht.named_entity_recognition(sent)) < 2:
                continue
            # 进行三元组抽取
            result = ht.triple_extraction(sent.strip())
            # 遍历本次三元组抽取的结果列表
            for one_triple in result:
                # 如果三元组已经在数据中了，则跳过
                if one_triple in SVOs:
                    continue

                # 对三元组中的sub进行命名实体识别，如果sub本身或者其中任意一个实体都不在词典中（即不是正常可读的词），则跳过
                flag = 0
                first = ht.named_entity_recognition(one_triple[0])  # 命名实体识别

                if one_triple[0] in entity_type_dict.keys():  # sub本身就在词典中
                    flag = 1
                else:
                    for entity in first.keys():
                        if entity in entity_type_dict.keys():  # sub的实体中有的在词典中
                            flag = 1
                            break
                # 如果以上条件都不满足，则跳过
                if flag == 0:
                    continue

                # 对obj做同样的操作
                flag = 0
                second = ht.named_entity_recognition(one_triple[2])
                if one_triple[2] in entity_type_dict.keys():
                    flag = 1
                else:
                    for entity in second.keys():
                        if entity in entity_type_dict.keys():
                            flag = 1
                            break
                if flag == 0:
                    continue

                # 符合条件就加入SVO中
                SVOs.append(one_triple)
    
    return SVOs


if __name__ == '__main__':
    plt.rcParams['font.sans-serif'] = ['SimHei']
    plt.rcParams['axes.unicode_minus'] = False 
    warnings.filterwarnings("ignore")

    # add_mention_dict = False  # 用来控制是否要分析别名（别名分析效果不好，而且也还没有成功加到模型里，改成True就会报错）

    ht = HarvestText()
    # 获得清华开放领域的词典，加入命名实体词典中
    entity_type_dict = establish_qh_dict()
    # 获得爬虫数据
    text_data = get_data()
    # 扩充词典
    ht, entity_type_dict = enrich_type_dict(text_data, ht, entity_type_dict)
    # 获得别名词典
    # if add_mention_dict:
    #     entity_mention_dict = get_mention_dict(text_data, ht)
    #     # 将命名实体词典加入到模型中
    #     ht.add_entities(entity_type_dict = entity_type_dict, entity_mention_dict = entity_mention_dict)
    # else:
    ht.add_entities(entity_type_dict = entity_type_dict)
    # 遍历所有的网页，进行三元组的抽取
    SVOs = extract_triple(text_data, ht, entity_type_dict)
    # 输出图像
    show_picture(SVOs)
    # 输出所有的三元组
    print(SVOs)
    # 保存数据
    save_data()
