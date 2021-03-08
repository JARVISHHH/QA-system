#-*-coding:utf-8-*-

import warnings
warnings.filterwarnings("ignore")

import urllib.request
from bs4 import BeautifulSoup
from queue import Queue
import time
import random
from urllib.parse import urljoin
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import os
import stat
import pickle as pkl
import tld
import lxml.html as lh
import re

"""
爬虫函数
对每一个url进行的操作：
在队列中的url一定是文本类型的，所以直接进行操作就行
1.获取这个url，获取失败，将该url加入到unvisited_urls中，然后退出
2.爬取文本中的正文内容，保存到字典中
3.获取网页的图片，进行保存。命名为 url id.png
4.获取这个url下面链接的所有网页
    对每一个url
    确认该网页是否已经在数据中（查找url是否存在于str_to_id字典中），如果已经在数据中，则直接将锚文本加入到这个url的字典中
    否则，确认该网页是否已经尝试过爬取（查找url是否存在于skip_urls中），如果在，则跳过
    否则
    - 用urllib爬取这个网页，确定网页的类型（若爬取失败，则直接pass）
        将网页加入skip_urls中
        - 对文本类型的网页
        （1）获取网页的title，如果锚文本、title、url中都没有任何和南开有关的信息，则这个网页不符合要求
        （2）给予其url id（加入转换的字典和列表中），将该网页加入text_url、和unvisited_urls中
        （3）如果title存在的话，将title加入该url的字典中
        （4）在该网页的字典中加入该锚文本，在父url的字典中加入该url及相应的锚文本
        - 对文档类型
        （1）给予其url id（加入转换的字典和列表中），将该网页加入doc_url中
        （2）将锚文本加入该url的字典中，在父url的字典中加入该url及相应的锚文本
"""

send_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36"\
    , "Connection": "keep-alive"
    }

class spider:

    def __init__(self):

        self.str_to_id = {}
        self.id_to_str = []

        self.skip_urls = []  # 包含已经爬取过、即将爬取的（在待访问队列中的） 以及 已经确认过与南开无关的网页
        self.unvisited_urls = Queue(maxsize = 0)
        self.text_url = {}

        self.pages = 20000  # 希望爬的总数（主要是想爬到一定阶段可以停下来，不用暴力关闭程序）
        self.num = 0

    def add_web(self, url, url_type = 0):
        """
        功能：将该url加入到对应的位置中。
        参数：url 要加入的参数   url_type 该url的类型，默认为0，即文本类型。其他数值都表示文档类型。
        """
        self.str_to_id[url] = len(self.id_to_str)
        self.id_to_str.append(url)
        if(url_type == 0):
            self.text_url[self.str_to_id[url]] = {"related url": {}, "text" : ''}
    
    def open_web(self):
        """
        功能：打开网页
        """
        chrome_options = Options()
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--start-maximized')
        # 打开浏览器
        self.driver = webdriver.Chrome(options = chrome_options)
        # 设置网页打开的超时时间
        self.driver.set_page_load_timeout(30)
    
    def getleftUrl(self):
        """
        功能：对队列中剩下的url进行处理，该方法在爬虫中断后调用，可继续之前的工作。
        """
        # 打开网页
        self.open_web()

        # t用来每隔50个url对爬取到的数据进行保存，防止中途发生意外导致之前爬到的数据都丢失了
        t = self.num // 50

        # 如果队列中还有待爬的url 并且 已经爬到的url数量还没要到达希望爬取的数量，则继续爬取
        while(not self.unvisited_urls.empty() and self.num < self.pages):
            # 从队列中获得当前url
            this_url = self.unvisited_urls.get()
            try:
                # 爬取当前url
                self.getSomeUrl(this_url)
                # 每爬50个进行保存
                if self.num // 50 > t:
                    self.save_url()
                    t = self.num // 50
                print("已经爬了" + str(self.num) + "个网页")
            except:
                print("整个失败 " + this_url)
                continue
        if self.unvisited_urls.empty():
            print("全部url遍历完毕")
        elif self.num >= self.pages:
            print("访问了" + str(self.pages) + "个url")
        # 打开浏览器
        self.driver.quit()
    
    def getAllUrl(self, head_url):
        """
        根据一个head_url获得所有扩展的url及其信息
        """
        # 将head_url加入数据中
        self.add_web(head_url)
        self.skip_urls.append(head_url)
        self.unvisited_urls.put(head_url)

        t = self.num // 50

        # 打开网页
        self.open_web()

        try:
            # 获得这个网页
            self.driver.get(head_url)
        except:
            print("网页获取失败 " + head_url)
            return
        
        self.num = 0
        # 循环进行爬虫，直到队列空了或者本次运行要爬取的量已经达到了预期
        while(not self.unvisited_urls.empty() and self.num < self.pages):
            # 从队列中获取下一个url
            this_url = self.unvisited_urls.get()
            try:
                # 对这个url进行处理
                self.getSomeUrl(this_url)
                if self.num // 50 > t:
                    self.save_url()
                    t = self.num // 50
                print("已经爬了" + str(self.num) + "个网页")
            except:
                print("整个失败 " + this_url)
                continue
            # time.sleep(random.random() + 0.5)
        print("总共爬了" + str(self.num) + "个网页")
        self.driver.quit()


    def getSomeUrl(self, url):
        '''
        功能：对单个url进行处理
        参数：url 要进行处理的网页（一定是文本类型的网页）
        '''
        try:
            # 获得这个网页
            self.driver.get(url)
        except:
            self.unvisited_urls.put(url)
            print("网页获取失败 " + url)
        
        # print(url)

        # 完整爬取到的页面+1
        self.num += 1

        # 获得url中的正文内容
        # 获取页面源代码
        html_source = self.driver.page_source
        
        # 重点
        html = lh.fromstring(html_source)
        # 获取标签下所有文本
        all_items = html.xpath("//text()")
        skip = []
        for path in ["//script//text()", "//nav//text()"]:
            skip.extend(html.xpath(path))
        items = []
        for item in all_items:
            if item not in skip:
                items.append(item)
        # 正则 匹配以下内容 \s+ 首空格 \s+$ 尾空格 \n 换行
        pattern = re.compile("^\s+|\s+$")
        clause_text = ""
        for item in items:
            # 将匹配到的内容用空替换，即去除匹配的内容，只留下文本
            line = re.sub(pattern, "", item)
            if len(line) > 0:
                clause_text += line + "\n"
        self.text_url[self.str_to_id[url]]["text"] = clause_text
        # print(self.text_url[self.str_to_id[url]]["text"])

        # 对子网页进行处理
        for father_tag in ['a', 'area']:
            try:
                tags = self.driver.find_elements_by_xpath("//" + father_tag)
            except:
                print("获得标签失败")
                continue
            for tag in tags:
                try:
                    link = tag.get_attribute("href")
                    # 若当前部分没有网址，则跳过
                    if type(link) == type(None):
                        continue
                    link = link.strip().strip('/')
                    # 跳过无效网址
                    if link == "None" or link == '' or "javascript:" in link or "http" not in link:
                        continue
                    if "cc.nankai.edu.cn" not in link:
                        continue
                    if link in self.skip_urls:
                        continue
                    
                    # 尝试对该网页进行爬取
                    try:
                        # print("尝试打开" + link)
                        req = urllib.request.Request(link, headers=send_headers)
                        response = urllib.request.urlopen(req, timeout = 30)
                        # print("访问成功 " + link)
                    except:
                        print("网址打开失败 " + link)
                        continue
                    self.skip_urls.append(link)

                    # 当前网页是文本网页
                    if response.headers['Content-Type'] == 'text/html':
                        # 尝试进行解码
                        try:
                            html = response.read().decode("utf-8")
                        except:
                            try:
                                html = response.read().decode("gb2312")
                            except:
                                print(link)
                                print("读取错误或解码错误")
                                continue
                        soup = BeautifulSoup(html, features='html.parser')

                        # 在数据中加入这个网页
                        self.add_web(link)
                        self.unvisited_urls.put(link)

                        self.text_url[self.str_to_id[link]]["text"] = ''
                    # 当前网页是文件网页
                    else:
                        continue
                except:
                    print("对一个网址操作错误")
                    continue


    def save_url(self):
        """
        功能：对所有的数据进行保存
        """
        queue_urls = []
        while(not self.unvisited_urls.empty()):
            url = self.unvisited_urls.get()
            queue_urls.append(url)
        with open(os.path.join(os.path.dirname(__file__), "url.txt"), "wb") as file:
            pkl.dump([self.num, self.str_to_id, self.id_to_str, self.skip_urls, self.text_url, queue_urls], file)
        for url in queue_urls:
            self.unvisited_urls.put(url)

    def get_url(self):
        """
        功能：获得所有保存的数据
        """
        with open(os.path.join(os.path.dirname(__file__), "url.txt"), "rb") as file:
            self.num, self.str_to_id, self.id_to_str, self.skip_urls, self.text_url, queue_urls = pkl.load(file)
        for url in queue_urls:
            self.unvisited_urls.put(url)


if __name__ == "__main__":

    start =time.clock()

    # 实例化爬虫类
    this_spider = spider()

    # 从南开官网开始爬虫（第一次开始爬时使用）
    this_spider.getAllUrl("https://cc.nankai.edu.cn/")

    # # 从文件中获得保存的数据
    # this_spider.get_url()
    # # 爬取剩下的url
    # this_spider.getleftUrl()
    # 保存类中的数据
    this_spider.save_url()

    end = time.clock()
    # 输出运行时长
    print('Running time: %s Seconds'%(end-start))