from harvesttext.harvesttext import HarvestText
from rdflib import URIRef,Graph,Namespace,Literal
from pyxdameraulevenshtein import damerau_levenshtein_distance as edit_dis
import numpy as np
import pickle as pkl
import os
from zincbase import KB

# 获得三元组数据
def get_data(path):
    with open(path, "rb") as file:
        SVOs, entity_type_dict = pkl.load(file)
    return SVOs, entity_type_dict

class NaiveKGQA:
    def __init__(self, SVOs=None, entity_mention_dict=None, entity_type_dict=None):
        self.ht_SVO = HarvestText()  # 三元组模型
        self.default_namespace = "https://github.com/JARVISHHH/"
        # 建图
        if SVOs:
            self.KG = self.build_KG(SVOs, self.ht_SVO)
        self.ht_e_type = HarvestText()  # 词典模型
        self.ht_e_type.add_entities(entity_mention_dict, entity_type_dict)  # 模型中加入词典
        # 类型到模板的字典
        self.q_type2templates = {():["default0"],
                                    ("#实体#",):["defaultE"],
                                    ("#谓词#",):["defaultV"],
                                    ("#实体#", "#谓词#"): ["defaultEV"],
                                    ("#实体#", "#实体#"): ["defaultEE"],
                                    ("#谓词#", "#实体#"): ["defaultVE"],}
        # 检索函数字典
        self.q_type2search = {():lambda *args: "",
                                ("#实体#",):lambda x: self.get_sparql(x=x),
                                ("#谓词#",):lambda y: self.get_sparql(y=y),
                                ("#实体#", "#谓词#"): lambda x,y: self.get_sparql(x=x, y=y),
                                ("#实体#", "#实体#"): lambda x,z: self.get_sparql(x=x, z=z),
                                ("#谓词#", "#实体#"): lambda y,z: self.get_sparql(y=y, z=z),}
        # 模板到答案的词典
        self.q_template2answer = {"default0":lambda *args: self.get_default_answer(),
                                    "defaultE":lambda entities, answers: self.get_default_answers(entities, answers),
                                    "defaultV": lambda entities, answers: self.get_default_answers(entities, answers),
                                    "defaultEV": lambda entities, answers: self.get_default_answers(entities, answers),
                                    "defaultEE": lambda entities, answers: self.get_default_answers(entities, answers),
                                    "defaultVE": lambda entities, answers: self.get_default_answers(entities, answers),}
    
    # 获得sparql查询语句
    def get_sparql(self, x=None, y=None, z=None, limit=None):
        quest_placeholders = ["", "", "", "", "", ""]
        for i, word in enumerate([x,y,z]):
            if word:
                quest_placeholders[i] = ""
                quest_placeholders[i + 3] = "ns1:"+word
            else:
                quest_placeholders[i] = "?x"+str(i)
                quest_placeholders[i + 3] = "?x"+str(i)

        # sparql查询语句填充
        query0 = """
            PREFIX ns1: <%s> 
            select %s %s %s
            where {
            %s %s %s.
            }
            """ % (self.default_namespace, quest_placeholders[0], quest_placeholders[1], quest_placeholders[2],
                    quest_placeholders[3], quest_placeholders[4], quest_placeholders[5])
        if limit:
            query0 += "LIMIT %d" % limit
        return query0

    # 默认回答（没找到答案）
    def get_default_answer(self, x = "", y = "", z = ""):
        if len(x+y+z) > 0:
            return x+y+z
        else:
            return "我没找到答案。"

    # 获得回答（有多个结果时）
    def get_default_answers(self, entities, answers):
        if len(answers) > 0:
            return "、".join("".join(x) for x in answers)
        else:
            return "我没找到答案。"

    # 创建知识图谱
    def build_KG(self, SVOs, ht_SVO):
        namespace0 = Namespace(self.default_namespace)  # 创建命名空间
        g = Graph()  # 建图
        type_word_dict = {"实体":set(),"谓词":set()}
        # 遍历所有的三元组，扩充词典并且将其加入图中
        for (s,v,o) in SVOs:
            try:
                type_word_dict["实体"].add(s)
                type_word_dict["实体"].add(o)
                type_word_dict["谓词"].add(v)
                g.add((namespace0[s.replace(" ", "")], namespace0[v.replace(" ", "")], namespace0[o.replace(" ", "")]))
            except:
                continue
        ht_SVO.add_typed_words(type_word_dict)
        return g

    # 解析问句
    def parse_question_SVO(self, question, pinyin_recheck=False, char_recheck=False):
        # 进行实体链接
        entities_info = self.ht_SVO.entity_linking(question,pinyin_recheck,char_recheck)
        entities, SVO_types = [], []
        # span范围，(x, type0)中x是词，type0是该词的类型
        for span,(x,type0) in entities_info:
            entities.append(x)  # 加入该实体
            SVO_types.append(type0)  # 加入该实体的类型
        # 直接提取前两个当作问题的关键词
        entities = entities[:2]
        SVO_types = tuple(SVO_types[:2])
        
        # 返回问句的实体及其类型
        return entities, SVO_types
    
    # 将问题的实体转换为实体类别
    def extract_question_e_types(self, question, pinyin_recheck=False, char_recheck=False):
        """
        参数: question 问题   pinyin_recheck 是否检查拼音   chat_recheck 是否检查字符
        """
        # 进行实体链接
        entities_info = self.ht_e_type.entity_linking(question, pinyin_recheck, char_recheck)
        question2 = self.ht_e_type.decoref(question, entities_info)
        # print("question2为：", question2)
        return question2
    
    # 匹配模板
    def match_template(self, question, templates):
        """
        参数：question 问题   templates 该问句匹配的所有的模板
        """
        # 计算每一个模板和当前模板的编辑距离
        arr = ((edit_dis(question, template0), template0) for template0 in templates)  # edit_dis()返回编辑距离
        # 选择编辑距离最小的模板
        dis, temp = min(arr)
        return temp
    
    # 获得答案的list
    def search_answers(self, search0):
        # 调用查询来获得结果
        records = self.KG.query(search0)
        answers = [[str(x)[len(self.default_namespace):] for x in record0] for record0 in records]
        return answers
    
    # 增加问题的模板
    def add_template(self, q_type, q_template, answer_function):
        """
        参数：q_type 槽位类型   q_template 问句模板   answer_function 回答模板
        """
        self.q_type2templates[q_type].append(q_template)  # 在词典中加入这一问句模板
        self.q_template2answer[q_template] = answer_function  # 在词典中加入这一回答模板
    
    # 获得答案的函数
    def answer(self, question, pinyin_recheck=False, char_recheck=False):
        # 解析问句，获得问句的关键词及其类别(去对应sparql的槽位)
        entities, SVO_types = self.parse_question_SVO(question,pinyin_recheck,char_recheck)
        # 尝试根据类别获得对应的sparsql，若是没有对应的sparql，直接返回理解无能
        try:
            search0 = self.q_type2search[SVO_types](*entities)  # 获得问题的sparql模式
        except:
            return "理解无能。"
        # print(search0)

        if len(search0) > 0:
            # 使用query在KG进行答案查找
            answers = self.search_answers(search0)
            # 根据问题的类型获得回答的所有模板
            templates = self.q_type2templates[SVO_types]
            # 将问句的实体转换为类别
            question2 = self.extract_question_e_types(question, pinyin_recheck, char_recheck)
            # 查找最合适的回答模板
            template0 = self.match_template(question2, templates)
            # 根据模板输出答案
            answer0 = self.q_template2answer[template0](entities,answers)
        else:
            answer0 = self.get_default_answer()
        return answer0

if __name__ == "__main__":
    # path = os.path.join(os.path.dirname(__file__), "data.txt")  # 爬取到的数据
    path = os.path.join(os.path.dirname(__file__), "faculty_data.txt")  # 人工标注的数据
    SVOs, entity_type_dict = get_data(path)

    QA = NaiveKGQA(SVOs, entity_type_dict=entity_type_dict)

    # 增加模板例子
    answer_func = lambda entities, answers: "他" + "、".join("".join(x) for x in answers) + "。"
    QA.add_template(("#实体#",), "#人名#干了哪些事？", answer_func)

    # 循环提问
    while(1):
        question = input("问：")
        if question == "exit":
            break
        print("答："+QA.answer(question))
    
    print("退出成功")